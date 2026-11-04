# Candidate pin from official indexed metadata; actual image/ABI/browser NOT_RUN.
# Never push this image or export its layers/cache. It contains the fixed asset.
FROM --platform=linux/amd64 mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f

# Copy only exact setup-action tool prefixes, never an existing virtualenv.
COPY tool-python/ /opt/hostedtoolcache/Python/3.12.14/x64/
COPY tool-node/ /opt/hostedtoolcache/node/24.22.1/x64/
ENV PATH="/opt/edgevision/backend/.venv-delivery/bin:/opt/hostedtoolcache/Python/3.12.14/x64/bin:/opt/hostedtoolcache/node/24.22.1/x64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    LD_LIBRARY_PATH=/opt/hostedtoolcache/Python/3.12.14/x64/lib \
    HOME=/home/edgevision CI=true ORT_DISABLE_TELEMETRY=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=Etc/UTC DEBIAN_FRONTEND=noninteractive
# Standard-library/version checks only. No ML import, probe or model execution.
RUN /opt/hostedtoolcache/Python/3.12.14/x64/bin/python3 -I -S -c \
    "import platform,sys; assert sys.version_info[:3] == (3,12,14); assert platform.machine() == 'x86_64'; assert sys.prefix == '/opt/hostedtoolcache/Python/3.12.14/x64'" \
    && test "$(/opt/hostedtoolcache/node/24.22.1/x64/bin/node --version)" = v24.22.1
WORKDIR /opt/edgevision
COPY source/ /opt/edgevision/
COPY asset/yolo11n.pt /opt/edgevision/asset/yolo11n.pt
# The installer creates a new venv here and installs only hash-locked wheels.
RUN groupadd --gid 10001 edgevision \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin edgevision \
    && /opt/hostedtoolcache/Python/3.12.14/x64/bin/python3 -I -S scripts/install_ml.py --delivery \
    && cd web && npm ci --ignore-scripts --no-audit --no-fund \
    && chown -R 10001:10001 /opt/edgevision /home/edgevision
USER 10001:10001
ENTRYPOINT ["/opt/edgevision/backend/.venv-delivery/bin/python"]
CMD ["/opt/edgevision/scripts/isolated_ml_entry.py"]
