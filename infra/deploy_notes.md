# Deploying to AWS EC2 (manual steps)

These steps are documentation only — nothing here is automated, and no AWS
resources are provisioned by the codebase itself. Run these manually from
your own machine/AWS console when you're ready to actually deploy.

## 1. Launch the instance

- EC2 → Launch instance → Amazon Linux 2023 (or Ubuntu 22.04), `t2.micro` /
  `t3.micro` (free-tier eligible).
- Security group: allow inbound `22` (SSH, restrict to your IP), `80` (HTTP).
  Do not open `8000` or `5432` publicly — those stay internal to the
  Docker network.
- Attach or create a key pair for SSH access.

## 2. Install Docker on the instance

```bash
sudo yum update -y                 # Amazon Linux; use apt-get on Ubuntu
sudo yum install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER      # log out/in for this to take effect
# Docker Compose plugin:
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/libexec/docker/cli-plugins/docker-compose
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
```

## 3. Get the code onto the instance

```bash
git clone <your-fork-url> trade-monitor
cd trade-monitor
cp .env.example .env
# Edit .env: set a real SECRET_KEY, DEBUG=False, ALLOWED_HOSTS=<public-ip-or-domain>,
# DB_ENGINE=postgres, and a real DB_PASSWORD.
```

## 4. Bring up the stack

```bash
docker compose up -d --build
docker compose logs -f web   # confirm migrate + seed_data ran, gunicorn started
```

This starts `db` (Postgres), `web` (gunicorn on :8000 inside the network),
`feed-generator`, and `detector` — the same four services as local dev, just
pointed at Postgres instead of SQLite.

## 5. Put nginx in front (host-level, not in compose)

Install nginx directly on the EC2 host (not in a container) so it can bind
to the security group's public `:80`:

```bash
sudo yum install -y nginx     # or apt-get install nginx
sudo cp infra/nginx.conf /etc/nginx/conf.d/trade-monitor.conf
```

Edit the copied config's `upstream` block to point at `127.0.0.1:8000`
(since `web`'s container port is published to the host in
`docker-compose.yml`), then:

```bash
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Static files: either mount the `static_volume` Docker volume path into
nginx's container (if running nginx in Compose instead) or run
`docker compose exec web python manage.py collectstatic` and copy
`staticfiles/` to a host path nginx can read.

## 6. Verify

Visit `http://<ec2-public-ip>/dashboard/` — you should see live-updating
orders and, within a minute or two, anomaly flags starting to appear.

## Notes / things intentionally left manual

- No HTTPS/ACM/Route53 setup here — add a domain + Let's Encrypt
  (`certbot --nginx`) if you want a real TLS cert; skipped to keep this
  project's infra footprint honest about what it actually demonstrates.
- No auto-scaling, load balancer, or RDS — a single `t3.micro` running
  Postgres in a container is intentionally proportionate to a portfolio
  demo, not a production trading system.
- To stop the feed generator (e.g. so the dashboard "freezes" at a known
  state for a demo), `docker compose stop feed-generator detector`.
