FROM python:3.12-slim-bookworm

# Use FreeTDS (pymssql/pyodbc friendly) instead of Microsoft's repo which
# currently fails signature verification on some systems. This avoids the
# packages.microsoft.com signing error during image builds.
RUN apt-get update && apt-get install -y --no-install-recommends \
        freetds-dev \
        freetds-bin \
        gcc \
        curl \
        ca-certificates \
        unixodbc \
        unixodbc-dev \
        tdsodbc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e .

RUN groupadd --system ikidgov && useradd --system --gid ikidgov --home /app ikidgov \
    && chown -R ikidgov:ikidgov /app
USER ikidgov

CMD ["sleep", "infinity"]
