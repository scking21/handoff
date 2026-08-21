FROM public.ecr.aws/docker/library/python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .[aws]

ENV HANDOFF_MODEL_PROVIDER=bedrock \
    HANDOFF_DATA_DIR=/tmp/handoff-data

EXPOSE 8080
CMD ["uvicorn", "handoff.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
