# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Installs all Python dependencies into /root/.local so the runtime image
# stays lean. TA-Lib requires the C shared library; we build it here too.
FROM python:3.11-slim AS builder

# System deps needed to compile TA-Lib C library and some Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build and install TA-Lib C library (required by ta-lib Python wrapper)
RUN wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.4.0/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make -j"$(nproc)" \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app

COPY requirements.txt .

# Install Python packages into user dir so they are copyable to runtime stage
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Lean image: copy compiled C library + Python site-packages from builder.
FROM python:3.11-slim

# Copy TA-Lib shared library from builder
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
COPY --from=builder /usr/include/ta-lib /usr/include/ta-lib

# Install minimal runtime system deps (curl for healthcheck, libgomp for numba)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages
COPY --from=builder /root/.local /root/.local

# Copy application source
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Non-root user for security
RUN useradd --create-home --shell /bin/bash made && chown -R made:made /app
USER made

EXPOSE 8000

# Healthcheck — relies on /health endpoint in api/main.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
