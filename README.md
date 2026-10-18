# cf-proxy-retry

A Cloudflare-routed HTTP proxy with automatic 429 retry logic, built for OpenCode free model access.

## What it does

Routes your API requests through Cloudflare's network (clean egress IPs that OpenCode doesn't flag as abusive), and **automatically retries on 429 rate limits** with exponential backoff until the request succeeds.

Eleanor's insight: when you hit a 429, just wait and retry — don't give up. This proxy does that for you.

## Architecture

```
Your App → cf-proxy-retry (127.0.0.1:8895) → Egress Provider → opencode.ai
                                              ├─ Cloudflare Relay (9router serverless)
                                              ├─ Vercel Relay (your own deployment)
                                              ├─ Netlify Relay (your own deployment)
                                              └─ Direct (local IP, no relay)
```

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

Copy `config.example.yaml` to `config.yaml` and fill in your settings:

```yaml
server:
  host: "127.0.0.1"
  port: 8895

# Pick your egress: cloudflare | vercel | netlify | direct
egress:
  provider: "cloudflare"
  cloudflare:
    # 9router's Cloudflare relay endpoint
    relay_url: "http://127.0.0.1:20128"
    api_key: "your-9router-api-key"
  vercel:
    relay_url: "https://your-app.vercel.app/api/relay"
    secret: "your-relay-secret"
  netlify:
    relay_url: "https://your-app.netlify.app/.netlify/functions/relay"
    secret: "your-relay-secret"

retry:
  max_retries: 10
  initial_delay: 5      # seconds
  max_delay: 60         # seconds
  backoff_multiplier: 2

queue:
  min_interval: 2.0     # seconds between requests
```

### 3. Run

```bash
python -m src.proxy_server
# or
python src/proxy_server.py
```

### 4. Use it

Point your HTTP client at the proxy:

```bash
# Via environment variables
export HTTP_PROXY=http://127.0.0.1:8895
export HTTPS_PROXY=http://127.0.0.1:8895

# Or configure your app directly
curl -x http://127.0.0.1:8895 https://opencode.ai/zen/v1/models
```

### 5. Health check

```bash
curl http://127.0.0.1:8895/health
```

## Deploying your own relay (Vercel)

For a **private** relay (your own egress IPs, not shared):

1. Go to [vercel.com](https://vercel.com) and create a new project
2. Copy the contents of `relay/vercel/` into your project
3. Set the `RELAY_SECRET` environment variable in Vercel dashboard
4. Deploy — you'll get a URL like `https://your-app.vercel.app`
5. Update `config.yaml`:
   ```yaml
   egress:
     provider: "vercel"
     vercel:
       relay_url: "https://your-app.vercel.app/api/relay"
       secret: "same-secret-as-vercel-env"
   ```

Same process for Netlify using `relay/netlify/`.

## Docker

```bash
docker build -t cf-proxy-retry .
docker run -d -p 8895:8895 -v ./config.yaml:/app/config.yaml cf-proxy-retry
```

Or with docker-compose:

```bash
docker-compose up -d
```

## How the 429 retry works

1. Request comes in → queued (min 2s spacing)
2. Forwarded through egress provider
3. If response is 429:
   - Log: `429 received, retry 1/10 in 5s...`
   - Wait 5s → retry
   - If still 429: wait 10s → retry
   - Backoff: 5s → 10s → 20s → 40s → 60s (capped)
   - After 10 retries, return the 429 to client
4. If success: return response immediately

Total max wait per request: ~5+10+20+40+60+60+60+60+60+60 = ~435s (~7 min)

## Why Cloudflare?

- Cloudflare's ASN (AS13335) is among the most trusted on the internet
- Blocking Cloudflare IPs would break ~20% of the web
- Serverless relays get fresh egress IPs per request (rotation built-in)
- Free tiers: 100k req/day (Workers), generous on Vercel/Netlify

**Note:** Cloudflare Workers *cannot* reach Cloudflare-fronted hosts (like opencode.ai). Use Vercel/Netlify relays or 9router's native relay instead.

## Config reference

See `config.example.yaml` for all options.

## License

MIT
