# Alpaca Stream — GCP Hosting Guide

> Goal: run the dashboard on a Google Cloud VM, reach it yourself over a secure SSH
> tunnel (never exposed to the public internet — it has live buy/sell endpoints and
> no login), keep code versioned on GitHub, and stop the VM overnight to save cost.

---

## Your current setup (already exists — nothing to create)

| What | Value |
|---|---|
| GCP Project | `project-062a1e95-5575-43f3-adf` |
| VM name | `instance-20260402-210914` |
| Zone | `us-central1-a` |
| Machine type | `c3-standard-4` (4 vCPU, 16 GB RAM) |
| Account | syed.ibrahim0723@gmail.com |

This is a much bigger (and pricier) machine than this app needs on its own — roughly
**~$140-150/month if left running 24/7**, versus ~$13/mo for a small e2-small VM.
That makes stopping it overnight/weekends genuinely worth doing, not just nice-to-have.
If this VM also runs other things you need the extra CPU for, leave it as is. If it's
only for this dashboard, you could resize it down later to cut costs further
(`gcloud compute instances set-machine-type` — VM must be stopped to resize).

The VM currently shows status `TERMINATED` (= stopped, not deleted) — no compute
charges while it's off, just disk storage.

---

## Part 1 — One-time GCP console checks

### Don't expose port 8000 publicly

`main.py` has live `/trade/buy`, `/trade/sell`, `/trade/cancel` endpoints with no
login and CORS wide open. If port 8000 is reachable from the internet, anyone who
finds the IP can place trades. So there should be **no** public firewall rule for
8000 — the only way in is an SSH tunnel (Part 5), gated by your GCP account/SSH key.

Check for and delete any old public rule:
```
gcloud compute firewall-rules list
gcloud compute firewall-rules delete allow-alpaca-8000
```

### External IP

```
gcloud compute instances describe instance-20260402-210914 --zone=us-central1-a --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```
This IP is ephemeral by default — it changes each time the VM stops/starts. That's
fine because `gcloud compute ssh` always looks up the current IP by instance name,
so the tunnel in Part 5 keeps working regardless. If you ever want a fixed IP:
```
gcloud compute addresses create alpaca-vm-ip --region=us-central1
gcloud compute instances delete-access-config instance-20260402-210914 --zone=us-central1-a --access-config-name="External NAT"
gcloud compute instances add-access-config instance-20260402-210914 --zone=us-central1-a --access-config-name="External NAT" --address=alpaca-vm-ip
```
Note: GCP charges a small fee (~$0.004/hr) for a static IP while the VM is stopped.

---

## Part 2 — gcloud CLI (already done)

You've already installed gcloud, run `gcloud init`, signed in as
`syed.ibrahim0723@gmail.com`, and set the default project to
`project-062a1e95-5575-43f3-adf` and zone to `us-central1-a`. Nothing more to do here.

---

## Part 3 — First-time app setup on the VM

Skip this if `main.py` is already running on this VM as a systemd service. If you're
not sure, start the VM and check (`sudo systemctl status alpaca-stream` over SSH) —
if that says "Unit not found," run this section.

### Start the VM
```
gcloud compute instances start instance-20260402-210914 --zone=us-central1-a
```
(or double-click `vm_start.bat`)

### SSH into the VM
```
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a
```
(First time: it generates SSH keys, say yes to prompts)

### Run the setup script (inside the SSH session)
```bash
bash ~/setup_vm.sh
```
> `setup_vm.sh` gets uploaded by `deploy.bat` automatically — or upload it manually:
> ```
> gcloud compute scp setup_vm.sh instance-20260402-210914:~/setup_vm.sh --zone=us-central1-a
> ```

Installs Python, creates the venv, installs dependencies, registers the systemd
service. Takes about 2 minutes. Type `exit` to leave the SSH session.

---

## Part 4 — Deploy your app (every time you update code)

`deploy.bat` is already configured with:
```bat
set PROJECT_ID=project-062a1e95-5575-43f3-adf
set VM_NAME=instance-20260402-210914
set ZONE=us-central1-a
```

### Double-click `deploy.bat`

It will:
1. **Commit and push your code to GitHub** — skipped automatically if nothing changed
2. Set the active GCP project
3. Copy `main.py`, `launcher.py`, `requirements.txt`, and `static/` to the VM
4. Upload `setup_vm.sh`
5. Upload your `.env` file securely (moved to `/opt/alpaca-stream/.env`)
6. Restart the service and print status

The VM must be **running** for steps 3-6 — run `vm_start.bat` first if it's stopped.

---

## Part 5 — Viewing the dashboard & managing the service

The dashboard is not public. To view it, open an SSH tunnel and leave the window open:
```
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a -- -L 8000:localhost:8000
```
Then browse to `http://localhost:8000` on your machine.

For a plain SSH session (no tunnel) to run commands:
```
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a
```

Then use these commands:
```bash
# Live logs (Ctrl+C to stop)
sudo journalctl -u alpaca-stream -f
# Status
sudo systemctl status alpaca-stream
# Restart after manual file edits
sudo systemctl restart alpaca-stream
# Stop / start
sudo systemctl stop alpaca-stream
sudo systemctl start alpaca-stream
```

The service **auto-starts on VM boot** (systemd handles it) — so after `vm_start.bat`,
the app is already running by the time the VM finishes booting (~20-30s).

### Controlling the VM itself (start/stop) from your laptop

- `vm_stop.bat` — stops the VM (no compute charges while off)
- `vm_start.bat` — starts the VM and prints the SSH tunnel command
- `setup_nightly_stop_task.bat` — **one-time** setup that registers a Windows
  Task Scheduler job to run `vm_stop.bat` automatically every night. Edit the
  `STOP_TIME` variable inside it first if 8:00 PM doesn't fit your schedule.
  This only fires while your PC is on — if you want the VM to stop even when
  your laptop is off, also set up a GCP-side instance schedule:
  ```
  gcloud compute resource-policies create instance-schedule alpaca-nightly-stop \
      --region=us-central1 \
      --vm-stop-schedule="0 20 * * *" \
      --timezone="America/New_York"
  gcloud compute instances add-resource-policies instance-20260402-210914 \
      --zone=us-central1-a --resource-policies=alpaca-nightly-stop
  ```

---

## Part 6 — Updating your .env on the VM

If your API keys change (e.g. Pulszy refresh token expires):

**Option A — via deploy.bat**
Update your local `.env` → double-click `deploy.bat` → it re-uploads `.env` and restarts.

**Option B — directly on the VM**
```bash
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a
sudo nano /opt/alpaca-stream/.env
# edit the key, save with Ctrl+O, exit with Ctrl+X
sudo systemctl restart alpaca-stream
```

---

## Quick Reference

| What | Command / URL |
|---|---|
| Deploy code (GitHub + VM) | double-click `deploy.bat` |
| Start VM | double-click `vm_start.bat` |
| Stop VM | double-click `vm_stop.bat` |
| Register nightly auto-stop | double-click `setup_nightly_stop_task.bat` (one-time) |
| View dashboard | `gcloud compute ssh instance-20260402-210914 --zone=us-central1-a -- -L 8000:localhost:8000` then open `http://localhost:8000` |
| Live logs | `gcloud compute ssh instance-20260402-210914 --zone=us-central1-a --command="sudo journalctl -u alpaca-stream -f"` |
| Get external IP | `gcloud compute instances describe instance-20260402-210914 --zone=us-central1-a --format="get(networkInterfaces[0].accessConfigs[0].natIP)"` |
| Estimated cost | ~$140-150/month if always on (c3-standard-4); much less if stopped overnight/weekends |

---

## Troubleshooting

**Can't reach the dashboard over the SSH tunnel?**
- Check the VM is running: `gcloud compute instances list`
- Confirm the tunnel command is still running in its own window (closing it kills the tunnel)
- SSH in and check: `sudo systemctl status alpaca-stream`

**Service won't start?**
```bash
sudo journalctl -u alpaca-stream -n 50 --no-pager
```
Usually a missing `.env` key or Python import error.

**deploy.bat fails on "file copy"?**
- Make sure the VM is running (not stopped)
- Try SSHing manually first: `gcloud compute ssh instance-20260402-210914 --zone=us-central1-a`

**Pulszy refresh token expired on VM?**
- Get new token from Chrome DevTools (Application → Cookies → `refreshToken`)
- Update `.env` locally → re-run `deploy.bat`
