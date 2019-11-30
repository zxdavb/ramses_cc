# evohome_cc

(WIP) HA custom_component for Honeywell Evohome RF protocol.

Uses https://github.com/zxdavb/evohome_rf (requires a Honeywell HGI80 or similar).

## Installation Instructions

Download the custom component in your custom_components folder, in `custom_components/evohome_rf` (best way):
```bash
git clone https://github.com/zxdavb/evohome_cc evohome_rf
```
... or (if you cant/wont be using git):
```bash
mkdir evohome_cc
curl -L https://api.github.com/repos/zxdavb/evohome_cc/tarball | tar xz -C evohome_cc --strip-components=1
```

Add the following to your configuration.yaml (required, and you need to set the port correctly):

```yaml
evohome_rf:
  port: /dev/ttyUSB0
```

Consider adding these two line to the logs section of your configuration.yaml (optional, and logging is a bit messy at the moment):

```yaml
logger:
  ...
  logs:
    homeassistant.components.evohome_rf: debug
    evohome: debug
   ....
```
Restart HA, and provide feedback via the HA forum:
https://community.home-assistant.io/t/honeywell-evohome-via-rf-hgi80-hgs80/151584
