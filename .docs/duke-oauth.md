# Duke OAuth (OIDC) Setup

## 1. Register Client

Go to [Duke Authentication Manager](https://manager.oit.duke.edu/express) and create a new OIDC client:

| Field | Value |
|-------|-------|
| Client Name | radchat |
| Redirect URI | `https://yourdomain.com/auth/callback` |
| Grant Type | authorization_code |
| Scopes | openid, profile, email |

Save the **Client ID** and **Client Secret**.

## 2. OIDC Endpoints

```
Authorization: https://oauth.oit.duke.edu/oidc/authorize
Token:         https://oauth.oit.duke.edu/oidc/token
UserInfo:      https://oauth.oit.duke.edu/oidc/userinfo
```

## 3. Environment Variables

```bash
DUKE_CLIENT_ID=radchat
DUKE_CLIENT_SECRET=<from step 1>
FLASK_SECRET_KEY=<random string for sessions>
```

## 4. GitHub Secrets (for deployment)

```bash
gh secret set DUKE_CLIENT_SECRET --body "<secret>"
gh secret set FLASK_SECRET_KEY --body "$(openssl rand -hex 32)"
```

## 5. Auth Flow

1. User clicks "Sign in with Duke"
2. Redirect to Duke OIDC authorize endpoint
3. User authenticates with NetID
4. Duke redirects back with authorization code
5. Server exchanges code for tokens
6. Server fetches user info from userinfo endpoint
