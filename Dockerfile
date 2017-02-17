FROM python:3.6

WORKDIR /app
ENV PYTHONPATH /app
EXPOSE 1988
COPY requirements.txt /app/
COPY stream_reader.py /app/
RUN pip install -r requirements.txt
# ENTRYPOINT ["python", "./stream_reader.py"]
