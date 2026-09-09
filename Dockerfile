FROM python:3.11-slim

WORKDIR /srv

# Dependencies in their own layer so a code change does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Non-root: nothing here needs to write to the filesystem, and a container that cannot
# escalate is one less thing to reason about when it runs someone else's scan output.
RUN useradd --create-home --uid 10001 findings
USER findings

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
