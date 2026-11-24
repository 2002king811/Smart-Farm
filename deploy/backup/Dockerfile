# pg_dump from the same major version as the database, plus the AWS CLI for off-site copies.
FROM postgres:16-alpine
RUN apk add --no-cache aws-cli tzdata
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh \
    && echo "30 1 * * * /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" > /etc/crontabs/root
CMD ["crond", "-f", "-l", "8"]
