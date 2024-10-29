# Use the base image
FROM docker/dev-environments-default:stable-1

RUN echo $USER

USER root

RUN echo "deb http://deb.debian.org/debian bullseye-backports main contrib non-free" >> /etc/apt/sources.list
RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y install python3-pip
RUN apt-get -y install -t bullseye-backports golang-go

USER vscode

RUN go install github.com/google/go-licenses@latest
