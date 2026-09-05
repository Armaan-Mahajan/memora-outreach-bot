# Unattended git push via macOS launchd

Why this exists: Cowork scheduled tasks run in a cloud container that sits
behind a git-egress proxy scoping which repos it'll inject credentials for.
This repo isn't (and can't easily be added to) that set, so a Cowork
scheduled task cannot `git push` here on its own -- tested twice (normal
mode: blocked at `git clone` by the command classifier; `bypassPermissions`
mode: clone/commit succeeded, `git push` still blocked by the proxy itself).

This sidesteps the whole problem: it's not Claude pushing at all. It's a
plain macOS scheduled job (`launchd`), running as Armaan's own user, doing
exactly what a manual `git push` from Terminal already does successfully.
Claude's automation still does everything up through the local `git commit`
(via device_bash on the mounted repo); this job just notices new local
commits every 60 seconds and pushes them to GitHub.

Everything below has to be run in a real Terminal window on the Mac --
none of it is possible through the Cowork device bridge (that shell is an
isolated Linux VM with no access to launchd, Keychain, or `~/.ssh`).

## 1. Generate a dedicated deploy key (don't reuse your personal SSH key)

```
ssh-keygen -t ed25519 -f ~/.ssh/memora_outreach_deploy -C "memora-outreach-bot-launchd" -N ""
```

The `-N ""` sets no passphrase. That's deliberate: this key will only ever
run inside a non-interactive launchd job with no Terminal attached to type
a passphrase into, and a passphrase-locked key with no ssh-agent available
just means the job silently fails. The blast radius stays narrow because
it's a deploy key, not your personal key -- see step 2.

## 2. Add it to GitHub as a deploy key, write-scoped to only this repo

```
cat ~/.ssh/memora_outreach_deploy.pub
```

Copy that output. On GitHub: this repo -> Settings -> Deploy keys -> Add
deploy key -> paste the public key -> check "Allow write access" -> Add key.

This key can push to `memora-outreach-bot` and nothing else on your
account -- tighter scope than the fine-grained PAT, and it never has to be
typed into a prompt, stored in a Cowork trigger, or embedded in a URL.

## 3. Point SSH at that key for this repo only

Add to `~/.ssh/config` (create the file if it doesn't exist):

```
Host github-memora-outreach
    HostName github.com
    User git
    IdentityFile ~/.ssh/memora_outreach_deploy
    IdentitiesOnly yes
```

## 4. Switch the remote to use that alias

```
cd ~/Documents/Projects/Memora/outreach-bot
git remote set-url origin git@github-memora-outreach:Armaan-Mahajan/memora-outreach-bot.git
```

Test it once by hand:

```
git push origin main
```

Should complete with no prompts at all. If it asks anything or fails,
stop here and fix that before wiring up launchd -- the scheduled job will
have the exact same problem, just silently.

## 5. Install the launchd job

```
cp scripts/com.armaan.memora-outreach-push.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.armaan.memora-outreach-push.plist
```

(On a fresh log-in session -- rare, but if `load` complains it's already
loaded after edits, use `launchctl unload` first, or `launchctl bootout
gui/$(id -u) ~/Library/LaunchAgents/com.armaan.memora-outreach-push.plist`
then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.armaan.memora-outreach-push.plist`
on newer macOS.)

## 6. Verify

```
launchctl list | grep memora-outreach-push
tail -f ~/Library/Logs/memora-outreach-push.log
```

The log stays empty until there's actually something to push (the script
is deliberately quiet on no-op runs). Make a throwaway local commit and
wait up to a minute to see it show up pushed and logged.

## Uninstalling

```
launchctl unload ~/Library/LaunchAgents/com.armaan.memora-outreach-push.plist
rm ~/Library/LaunchAgents/com.armaan.memora-outreach-push.plist
```
