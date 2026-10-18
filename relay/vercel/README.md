# Vercel Relay Deployment

1. Create a new project at [vercel.com](https://vercel.com)
2. Copy the `api/` directory and `vercel.json` into your project root
3. In Vercel dashboard → Settings → Environment Variables, add:
   - `RELAY_SECRET` = a random secret string (e.g. `openssl rand -hex 32`)
4. Deploy
5. Your relay URL: `https://your-app.vercel.app/api/relay`
6. Update `config.yaml`:
   ```yaml
   egress:
     provider: "vercel"
     vercel:
       relay_url: "https://your-app.vercel.app/api/relay"
       secret: "same-secret-as-above"
   ```

## Testing

```bash
curl https://your-app.vercel.app/api/relay \
  -H "X-Relay-Secret: your-secret" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","url":"https://httpbin.org/ip","headers":{},"body":null}'
```
