# Zscaler + Docker (Colima) SSL Certificate Troubleshooting

## Problem

`npm run aws:deploy` (CDK deploy) fails during Python Lambda bundling with:

```
pip install --upgrade pip
  WARNING: pip is configured with locations that require TLS/SSL,
  however the ssl module in Python is not available.
  ...
  ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
  certificate verify failed: unable to get local issuer certificate
```

This happens because CDK builds Python Lambda functions inside Docker containers (via Colima on macOS), and the Zscaler corporate proxy intercepts all HTTPS traffic with its own CA certificate. Docker containers don't trust the Zscaler CA by default.

## Why the Security Team's Script Doesn't Fix This

The security team's recommended script sets three environment variables in `~/.zshrc`:

```bash
export REQUESTS_CA_BUNDLE=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
export NODE_EXTRA_CA_CERTS=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
export SSL_CERT_FILE=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
```

These variables **only fix host-level tools** (Python requests, Node.js, OpenSSL on your Mac). They do **not** fix Docker containers because:

1. **Docker containers have isolated environments.** Host env vars are not inherited by containers unless explicitly passed via `-e` or `--env-file`.
2. **Colima uses sshfs to mount only `/Users/` into the VM.** The certificate file at `/usr/local/share/zscaler-certificates/` is not accessible inside Colima's Docker VM — Colima only mounts the user's home directory by default. Attempting to volume-mount `/usr/local/share/...` into a container results in an empty directory, not the file.
3. **CDK Python bundling has two Docker stages**, and each needs separate handling:
   - **Docker BUILD** (`Dockerfile` → `RUN pip install --upgrade pip`): Baked into the Docker image layer. No env vars or volumes from CDK bundling options apply here.
   - **Docker RUN** (`pip install -r requirements.txt` during bundling): This is where CDK's `BundlingOptions` (environment, volumes) take effect.

### Visual summary

```
┌─ macOS Host ──────────────────────────────────────────────┐
│  ~/.zshrc env vars ✅ → Python, Node.js, curl work fine   │
│                                                           │
│  ┌─ Colima VM (sshfs: /Users/ only) ───────────────────┐ │
│  │  /usr/local/share/zscaler-certificates/ ❌ NOT HERE  │ │
│  │                                                      │ │
│  │  ┌─ Docker Container ────────────────────────────┐  │ │
│  │  │  Host env vars ❌ NOT INHERITED               │  │ │
│  │  │  pip install → SSL_CERT_VERIFY_FAILED ❌      │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

## How We Fixed It

### Prerequisites

1. **Zscaler Root CA** (`~/zscaler-root-ca.pem`): Export from Keychain Access → System Roots → "Zscaler Root CA" → File → Export Items → PEM format.
2. **Zscaler Certificate Bundle** (`/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem`): Install via Self Service → "Zscaler Certificate Bundle".

### Step 1: Create a combined CA bundle

macOS system certs (`/etc/ssl/cert.pem`) do NOT include the Zscaler CA, even after installing the Zscaler Certificate Bundle. We need to manually combine them:

```bash
cat /etc/ssl/cert.pem ~/zscaler-root-ca.pem > ~/combined-ca-bundle.pem
```

This file must live under `/Users/` so Colima's sshfs mount can access it inside the Docker VM.

### Step 2: CDK bundling configuration (`lambda-stack.ts`)

The `getBundlingOptions()` method mounts the combined bundle into Docker containers and sets the necessary env vars:

```typescript
private getBundlingOptions(): BundlingOptions {
  const zscalerCert = path.join(os.homedir(), 'combined-ca-bundle.pem');
  const hostCertPath = fs.existsSync(zscalerCert) ? zscalerCert : '/etc/ssl/cert.pem';
  const hasCert = fs.existsSync(hostCertPath);
  const containerCertPath = '/etc/ssl/certs/ca-certificates.crt';
  const volumes: DockerVolume[] = hasCert
    ? [{ hostPath: hostCertPath, containerPath: containerCertPath }]
    : [];
  return {
    environment: {
      UV_NATIVE_TLS: 'true',
      ...(hasCert && {
        SSL_CERT_FILE: containerCertPath,
        PIP_CERT: containerCertPath,
        REQUESTS_CA_BUNDLE: containerCertPath
      })
    },
    volumes
  };
}
```

Key points:
- **`PIP_CERT`** is the env var pip actually respects for CA verification (not `SSL_CERT_FILE` alone).
- **`REQUESTS_CA_BUNDLE`** is for the Python `requests` library.
- **`SSL_CERT_FILE`** is for general OpenSSL-based tools.
- **`UV_NATIVE_TLS`** tells `uv` (the Python package manager) to use the system's native TLS stack.
- The volume mount replaces the container's default CA bundle with our combined bundle.

### Step 3: Docker BUILD stage workaround

The CDK Python alpha module's Dockerfile (`node_modules/@aws-cdk/aws-lambda-python-alpha/lib/Dockerfile`) runs `pip install --upgrade pip` during the Docker BUILD stage, before any bundling volumes or env vars are applied. To fix this:

```bash
# One-time: add --trusted-host flags to the Dockerfile
# This gets cached in the Docker image layer
sed -i '' 's/pip install --upgrade pip/pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --upgrade pip/g' \
  node_modules/@aws-cdk/aws-lambda-python-alpha/lib/Dockerfile
```

> **Note:** This modification lives in `node_modules/` and will be overwritten on `npm install`. However, the Docker image layer is cached, so it persists across deploys until `docker builder prune` is run. If you clear Docker cache and see the error again, re-run the sed command above.

### Step 4: Set host env vars (for non-Docker tools)

Add to `~/.zshrc` (the security team's script — still needed for host-level tools):

```bash
export REQUESTS_CA_BUNDLE=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
export NODE_EXTRA_CA_CERTS=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
export SSL_CERT_FILE=/usr/local/share/zscaler-certificates/ZscalerRoot-FullBundle.pem
```

## Quick Reference: What Fixes What

| Layer | Problem | Solution |
|-------|---------|----------|
| macOS host tools | `pip`, `node`, `curl` can't verify Zscaler SSL | `~/.zshrc` env vars (security team script) |
| Docker RUN stage | `pip install -r requirements.txt` fails in CDK bundling | `getBundlingOptions()` — volume mount + `PIP_CERT` env var |
| Docker BUILD stage | `pip install --upgrade pip` fails in Dockerfile | `--trusted-host` flags in Dockerfile (cached in image layer) |
| `uv` (Python pkg mgr) | uv can't verify SSL when syncing deps | `UV_NATIVE_TLS=true` in bundling env and `package.json` scripts |

## If It Breaks Again

1. **After `npm install`**: The Dockerfile hack is gone. If Docker cache is also cleared, re-run the sed command from Step 3.
2. **After `docker builder prune`**: Docker BUILD stage cache is lost. Re-run `npm run aws:deploy` — it will rebuild the image (may need the sed command first).
3. **After macOS system cert update**: Regenerate the combined bundle: `cat /etc/ssl/cert.pem ~/zscaler-root-ca.pem > ~/combined-ca-bundle.pem`
4. **New machine setup**: Follow all 4 steps above. The `combined-ca-bundle.pem` file is not checked into the repo (it's machine-specific).
