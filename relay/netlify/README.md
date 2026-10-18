# Netlify Relay Deployment

1. Create a new site at [netlify.com](https://netlify.com)
2. Copy the `functions/` directory into your project (Netlify auto-detects it)
   - Or set functions directory in `netlify.toml`:
     ```toml
     [functions]
       directory = "functions"
     ```
3. In Netlify dashboard → Site settings → Environment variables, add:
   - `RELAY_SECRET` = a random secret string
4. Deploy
5. Your relay URL: `https://your-app.netlify.app/.netlify/functions/relay`
6. Update `config.yaml`:
   ```yaml
   egress:
     provider: "netlify"
     netlify:
       relay_url: "https://your-app.netlify.app/.netlify/functions/relay"
       secret: "same-secret-as-above"
   ```
