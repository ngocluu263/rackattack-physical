# Rackattack Physical
FROM centos
MAINTAINER eliran@stratoscale.com

# Add the EPEL repository and update all packages
RUN yum install -y wget; \
    wget http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm && \
    rpm -ivh epel-release-7-5.noarch.rpm && \
    rm epel-release-7-5.noarch.rpm

# Install other tools
RUN yum update -y && \
    yum install -y \
    git \
    ipmitool \
    python-devel \
    python-pip \
    make \
    sudo \
    boost-devel \
    boost-static \
    openssl-devel \
    gcc-c++ \
    which && \
    yum -y clean all

RUN pip install pep8

# Edit sudoers file to avoid error: sudo: sorry, you must have a tty to run sudo
RUN sed -i -e "s/Defaults    requiretty.*/ #Defaults    requiretty/g" /etc/sudoers

WORKDIR /root

# Install solvent
RUN git clone https://github.com/Stratoscale/solvent && \
    make -C solvent install && \
    rm -rf solvent upseto

# Install Osmosis
RUN git clone https://github.com/Stratoscale/osmosis && \
    make -C osmosis build -j 10 && \
    make -C osmosis install_binary && \
    rm -rf osmosis

# Install Inaugurator
RUN git clone https://github.com/Stratoscale/inaugurator && \
    git --work-tree=inaugurator --git-dir=inaugurator/.git checkout v1.2.1 && \
    BUILD_HOST=local IMAGES_SOURCE=remote make install -C inaugurator && \
    rm -rf inaugurator

RUN mkdir work

ADD . /root/work/rackattack-physical/

RUN cd work && \
    mv rackattack-physical/build/rackattack-{virtual,api}/ . && \
    cd rackattack-physical && \
    upseto fulfillRequirements && \
    make validate_requirements && \
    cd ../rackattack-virtual && \
    git checkout dnsmasq-eth1 && \
    cd - && \
    make build SKIP_REQUIREMENTS=1 && \
    mkdir /usr/share/rackattack.physical && \
    cp -rf build/*.egg /usr/share/rackattack.physical/ && \
    cd .. && \
    rm work -rf
