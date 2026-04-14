# Lightsail + GitHub Actions Auto-Deploy

## Overview

Deploy the Topology Maps project to an AWS Lightsail instance with automatic
redeployment on every push to `main` via GitHub Actions.

## Architecture

```
git push to main
       ↓
GitHub Actions triggers
       ↓
SSH into Lightsail
       ↓
git pull → docker compose up -d --build
       ↓
Site live at http://<LIGHTSAIL_IP>
```

## Infrastructure

| Component        | Detail                              |
|------------------|-------------------------------------|
| Instance         | AWS Lightsail, Ubuntu 24.04         |
| Plan             | $10/month (2 GB RAM, 1 vCPU)       |
| Exposed ports    | 80 (HTTP), 22 (SSH)                 |
| CI/CD            | GitHub Actions (free tier)          |
| Containers       | simulator, server, ui (via Compose) |

Only the UI port (80) is publicly accessible. The server API and simulator
communicate internally over the Docker bridge network. Nginx inside the UI
container reverse-proxies `/api/` and `/ws/` to the server container.

---

## Step-by-Step Setup

### Step 1 — Create a Lightsail Instance

1. Open the [AWS Lightsail console](https://lightsail.aws.amazon.com)
2. Click **Create instance**
3. Choose:
   - **Region**: closest to you
   - **Platform**: Linux/Unix
   - **Blueprint**: OS Only → **Ubuntu 24.04 LTS**
   - **Plan**: $10/month (2 GB RAM)
   - **Instance name**: `topology-maps`
4. Click **Create instance**
5. Once running, note the **Public IP** shown on the instance card

### Step 2 — Open Port 80 in the Firewall

1. Click on your instance → **Networking** tab
2. Under **IPv4 Firewall**, click **Add rule**
3. Set **Application**: HTTP (port 80)
4. Click **Create**

(SSH on port 22 is open by default.)

### Step 3 — SSH into the Instance

From the Lightsail console, click the terminal icon on your instance, or use
the default key pair Lightsail created:

```bash
ssh -i ~/.ssh/LightsailDefaultKey-<region>.pem ubuntu@<YOUR_LIGHTSAIL_IP>
```

(You can download this key from the Lightsail console under **Account → SSH keys**.)

### Step 4 — Install Docker

Run these commands on the Lightsail instance:

```bash
# Install Docker using the official convenience script
curl -fsSL https://get.docker.com | sudo sh

# Let the ubuntu user run Docker without sudo
sudo usermod -aG docker ubuntu

# Apply the group change (or log out and back in)
newgrp docker

# Verify Docker works
docker --version
docker compose version
```

### Step 5 — Create a Deploy Key for GitHub Actions

Still on the Lightsail instance:

```bash
# Generate an SSH key pair for GitHub Actions
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N "" -C "github-actions-deploy"

# Authorize it to log in to this machine
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys

# Print the PRIVATE key — you will copy this into GitHub in Step 7
cat ~/.ssh/deploy_key
```

Copy the entire private key output (including the `-----BEGIN` and `-----END`
lines). You will paste this into GitHub in Step 7.

### Step 6 — Clone the Repo and Do the First Deploy

Still on the Lightsail instance:

```bash
# Clone your repository
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git ~/topology-maps

# Start the application
cd ~/topology-maps
docker compose up -d --build
```

The first build takes a few minutes. Once done, visit `http://<YOUR_LIGHTSAIL_IP>`
in your browser to verify the app is running.

### Step 7 — Add GitHub Secrets

1. Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** and add these two secrets:

| Secret name          | Value                                        |
|----------------------|----------------------------------------------|
| `LIGHTSAIL_HOST`     | Your Lightsail instance's public IP address   |
| `LIGHTSAIL_SSH_KEY`  | The full private key from Step 5              |

### Step 8 — Push and Test

The `.github/workflows/deploy.yml` file in this repo handles the rest. Push
any change to `main` and watch the **Actions** tab in GitHub — your Lightsail
instance will automatically pull and redeploy.

---

## GitHub Secrets Reference

| Secret               | Description                          |
|----------------------|--------------------------------------|
| `LIGHTSAIL_HOST`     | Public IP of the Lightsail instance  |
| `LIGHTSAIL_SSH_KEY`  | ED25519 private key created in Step 5|

## Maintenance

- **View logs**: `ssh` into the instance, then `cd ~/topology-maps && docker compose logs -f`
- **Restart**: `docker compose restart`
- **Rebuild from scratch**: `docker compose down && docker compose up -d --build`
- **Check disk space**: `df -h` (the $10 plan has 60 GB)

## Future Improvements (Not in Scope Now)

- Add HTTPS via Let's Encrypt + Certbot
- Attach a custom domain via Lightsail DNS
- Set up a static IP to survive instance restarts
