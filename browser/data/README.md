# Browser data bundled with releases

Release builds place the latest checksum-verified GeoIP snapshot and the signed
uBlock Origin XPI pinned by `../assets.lock.json` in this directory. GeoIP's
`geoip-aio-all-latest.mmdb.json` records the resolved release, URL and SHA-256;
installation uses that snapshot without contacting upstream. Do not commit these
binary assets or generated snapshot metadata to the source repository.

## uBlock Origin

Upstream: [gorhill/uBlock](https://github.com/gorhill/uBlock).
The original Mozilla XPI is bundled without modification, retaining its signature
and included `LICENSE.txt` and third-party notices. Installation verifies the
archive hash and manifest version before loading the extension.

## GeoIP

Upstream: [daijro/geoip-all-in-one](https://github.com/daijro/geoip-all-in-one).
Its [source list and attributions](https://github.com/daijro/geoip-all-in-one#licenses)
include:

- IP2Location LITE: https://lite.ip2location.com/
- GeoLite2: this product includes GeoLite2 Data created by MaxMind,
  available from https://www.maxmind.com/.
- DB-IP Lite: https://db-ip.com/
- Further country data sources are listed in the upstream README.
