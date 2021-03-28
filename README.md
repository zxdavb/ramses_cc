## Overview
**evohome_cc** is a HA custom component that works with some Honeywell 868 MHz RF-based systems such as **evohome**, **Sundial**, **Hometronic**, **Cohronotherm** and many others.  

The simplest way to know if it will work with your system is to identify the box connected to your boiler (or other heat source) to one of (there will be other systems that also work):
 - **R8810A**: OpenTherm Bridge
 - **BDR91A**: Wireless Relay
 - **HC60NG**: Wireless Relay (older hardware version)

It requires a serial-to-RF devices, either a Honeywell HGI80 (rare, expensive), or a 868 MHz nanoCUL (eBay, ~EUR25, don't buy the 433 MHz version) running [evofw3](https://github.com/ghoti57/evofw3).

It uses the [evohome_rf](https://github.com/zxdavb/evohome_rf) client library to decode the RAMSES-II protocol used by these devices. Note that other systems, such as HVAC, also use this protocol, YMMV.

See the [wiki](https://github.com/zxdavb/evohome_cc/wiki) for installation, configuration, troubleshooting, etc.
