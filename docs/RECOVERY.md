# Recovery Guide — Locked Out of node1

If the bootstrap failed partway through and node1 is unreachable, the security role may have applied the hardened SSH config (port 2222, root disabled) before the deploy password was set.

## Use Contabo VNC Console

1. Log in to [Contabo Customer Panel](https://contabo.com/en/customer/)
2. Open your VPS → **VNC** or **Console**
3. Log in as `root` with your password (console access doesn’t use SSH)

## Restore SSH Access

Once on the console, run:

```bash
# 1. Revert main sshd_config
sed -i 's/^Port 2222/Port 22/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i '/^AllowUsers/d' /etc/ssh/sshd_config

# 2. Check for drop-in configs and /etc/default/ssh (Ubuntu uses SSHD_OPTS)
grep -r "Port\|2222" /etc/ssh/sshd_config.d/ || true
cat /etc/default/ssh
# If SSHD_OPTS="-p 2222" or similar, edit /etc/default/ssh and remove or change it

# 3. Allow port 22 in UFW
ufw allow 22/tcp
ufw reload

# 4. Restart SSH
systemctl restart ssh   # Debian/Ubuntu
# or: systemctl restart sshd   # RHEL

# 5. Verify
grep "^Port" /etc/ssh/sshd_config
systemctl status ssh
```

If SSH still shows port 2222 after restart, a file in `/etc/ssh/sshd_config.d/` may be overriding. List and edit/remove: `ls /etc/ssh/sshd_config.d/`

## Bootstrap Again

Update `inventory/hosts.yml` so both nodes use `ansible_user: root` and `ansible_port: 22`, then run:

```bash
ansible-playbook playbooks/bootstrap.yml -i inventory/hosts.yml -k --ask-vault-pass
```

The security role is now ordered so that SSH is restarted only after the deploy password is set successfully, so a vault error will no longer cause a lockout.
