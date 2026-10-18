# NordVPN Dynamic Bridge

HTTP API to control NordVPN location switching with fraud-detection safeguards.

## API (127.0.0.1:1442)

- `GET /status` - current location, egress IP, cooldown
- `POST /change_location` - switch to random location
- `POST /change_location {"location": "se"}` - switch to specific country

## Proxy

Dynamic container exposes proxy on 127.0.0.1:1444 (changes with location).

## Safety

- 75-second cooldown between switches (prevents NordVPN fraud detection)
- 17 countries supported
- Uses existing NordVPN credentials from ~/gluetun/nordvpn.env
