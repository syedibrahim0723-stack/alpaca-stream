# Alpaca Stream — GCP Hosting Guide

> Goal: run the dashboard on a Google Cloud VM so you can reach it at `http://<IP>:8000` from any browser.

---

## Part 1 — One-time GCP Console Setup

### Step 1 — Create a project

1. Go to https://console.cloud.google.com
2. Click the project dropdown (top-left, next to "Google Cloud") → **New Project**
3. Name it `alpaca-stream-live` → **Create**
4. Wait ~10 seconds, then select it from the dropdown

### Step 2 — Enable Compute Engine

1. In the left menu → **Compute Engine** → **VM instances**
2. If prompted, click **Enable** (takes ~1 min to activate billing)

### Step 3 — Create the VM

1. Click **Create Instance**
2. Fill in:

| Field | Value |
|---|---|
| Name | `alpaca-stream-vm` |
| Region | `us-east1` (Virginia — lowest latency to Alpaca SIP) |
| Zone | `us-east1-b` |
| Machine type | `e2-small` (2 vCPU, 2 GB RAM — enough, ~$13/mo) |
| Boot disk OS | Ubuntu 22.04 LTS |
| Boot disk size | 20 GB (default is fine) |
| Firewall | ✅ Allow HTTP traffic |

3. Click **Create** — VM takes ~30 seconds to start

### Step 4 — Open port 8000

The app runs on port 8000 (not standard 80), so you need a firewall rule.

1. In the left menu → **VPC network** → **Firewall**
2. Click **Create Firewall Rule**
3. Fill in:

| Field | Value |
|---|---|
| Name | `allow-alpaca-8000` |
| Network | `default` |
| Direction | Ingress |
| Action | Allow |
| Targets | All instances in the network |
| Source filter | IP ranges |
| Source IP ranges | `0.0.0.0/0` |
| Protocols and ports | TCP `8000` |

4. Click **Create**

### Step 5 — Note your external IP

1. Back in **Compute Engine → VM instances**
2. Find `alpaca-stream-vm` — copy the **External IP** (e.g. `34.73.12.45`)
3. Your dashboard will be at: `http://34.73.12.45:8000`

---

## Part 2 — Install gcloud CLI on Windows (one-time)

1. Download installer: https://cloud.google.com/sdk/docs/install
   (Click "Windows" → download the `.exe` installer)
2. Run the installer, keep all defaults
3. At the end, a terminal opens — run:
   ```
   gcloud init
   ```
4. Sign in with your Google account, select `alpaca-stream-live` as the project

---

## Part 3 — First-time VM setup

Open **Command Prompt** and run these two commands:

### SSH into the VM
```
gcloud compute ssh alpaca-stream-vm --zone=us-east1-b
```
(First time: it generates SSH keys, say yes to prompts)

### Run the setup script (inside the SSH session)
```bash
# You're now inside the VM
bash ~/setup_vm.sh
```

> `setup_vm.sh` will be uploaded by `deploy.bat` on first run, or you can upload it manually:
> ```
> gcloud compute scp setup_vm.sh alpaca-stream-vm:~/setup_vm.sh --zone=us-east1-b
> ```

The script installs Python, creates the venv, installs all dependencies, and registers the systemd service. This takes about 2 minutes.

Type `exit` to leave the SSH session.

---

## Part 4 — Deploy your app (every time you update code)

### Edit `deploy.bat` — set your project/VM name at the top:
```bat
set PROJECT_ID=alpaca-stream-live
set VM_NAME=alpaca-stream-vm
set ZONE=us-east1-b
```

### Double-click `deploy.bat`

It will:
1. Set the active GCP project
2. Copy `main.py`, `launcher.py`, `requirements.txt`, and `static/` to the VM
3. Upload `setup_vm.sh`
4. Upload your `.env` file securely (moved to `/opt/alpaca-stream/.env`)
5. Restart the service
6. Print your dashboard URL

---

## Part 5 — Managing the service

SSH into the VM anytime:
```
gcloud compute ssh alpaca-stream-vm --zone=us-east1-b
```

Then use these commands:

```bash
# Live logs (Ctrl+C to stop)
sudo journalctl -u alpaca-stream -f

# Status
sudo systemctl status alpaca-stream

# Restart after manual file edits
sudo systemctl restart alpaca-stream

# Stop
sudo systemctl stop alpaca-stream

# Start
sudo systemctl start alpaca-stream
```

The service **auto-starts on VM reboot** (systemd handles it).

---

## Part 6 — Updating your .env on the VM

If your API keys change (e.g. Pulszy refresh token expires):

**Option A — via deploy.bat**
Update your local `.env` → double-click `deploy.bat` → it re-uploads `.env` and restarts.

**Option B — directly on the VM**
```bash
gcloud compute ssh alpaca-stream-vm --zone=us-east1-b
sudo nano /opt/alpaca-stream/.env
# edit the key, save with Ctrl+O, exit with Ctrl+X
sudo systemctl restart alpaca-stream
```

---

## Quick Reference

| What | Command / URL |
|---|---|
| Dashboard | `http://<EXTERNAL_IP>:8000` |
| Flow diagram | `http://<EXTERNAL_IP>:8000/flow.html` |
| Alerts log | `http://<EXTERNAL_IP>:8000/log/alerts` |
| Live logs | `gcloud compute ssh alpaca-stream-vm --zone=us-east1-b --command="sudo journalctl -u alpaca-stream -f"` |
| Get external IP | `gcloud compute instances describe alpaca-stream-vm --zone=us-east1-b --format="get(networkInterfaces[0].accessConfigs[0].natIP)"` |
| Stop VM (save $) | GCP Console → VM instances → ⋮ → Stop |
| Estimated cost | ~$13/month (e2-small, always on) |

---

## Troubleshooting

**Can't reach the dashboard?**
- Check the VM is running in GCP Console
- Confirm firewall rule `allow-alpaca-8000` exists
- SSH in and check: `sudo systemctl status alpaca-stream`

**Service won't start?**
```bash
sudo journalctl -u alpaca-stream -n 50 --no-pager
```
Usually a missing `.env` key or Python import error.

**deploy.bat fails on "file copy"?**
- Make sure the VM is running (not stopped)
- Try SSHing manually first: `gcloud compute ssh alpaca-stream-vm --zone=us-east1-b`

**Pulszy refresh token expired on VM?**
- Get new token from Chrome DevTools (Application → Cookies → `refreshToken`)
- Update `.env` locally → re-run `deploy.bat`
