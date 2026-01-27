# Duke OIDC Integration

## Setup Steps

1. **Create Support Group** at [Group Manager](https://groups.oit.duke.edu/groupmanager/myGroups/viewCreateGroup)
   - Create Ad Hoc group with descriptive name
   - Add yourself as owner and member

2. **Request Support Group Promotion** from group page
   - Add group description
   - Provide reason (e.g., "OAuth client registration for [project]")
   - Wait for approval

3. **Register OAuth Client** at [OAuth Registration](https://authentication.oit.duke.edu/manager/oauth/register)
   - Select your support group
   - Configure as public client (no secret) for browser apps
   - Add redirect URIs for all environments

4. **Implement auth** using `shared/auth.js` module

## Client

- **Client ID**: `interactiveai`
- **Redirect URI**: `https://edu-artifacts.github.io/interactive-ai/`

## Endpoints

| Endpoint | URL |
|----------|-----|
| Authorization | https://oauth.oit.duke.edu/oidc/authorize |
| Token | https://oauth.oit.duke.edu/oidc/token |
| UserInfo | https://oauth.oit.duke.edu/oidc/userinfo |
| JWKS | https://oauth.oit.duke.edu/oidc/jwk |

## Resources

- [Duke OIDC Server](https://oauth.oit.duke.edu/oidc/)
- [Authentication Manager](https://authentication.oit.duke.edu/manager)
- [OAuth FAQ](https://authentication.oit.duke.edu/manager/oauth/faq)
