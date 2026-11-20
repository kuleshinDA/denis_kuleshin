FROM python:3.12.10-slim
RUN pip install --no-cache-dir py-spy==0.4.1
ENTRYPOINT ["py-spy"]
