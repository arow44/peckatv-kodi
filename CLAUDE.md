# plugin.video.peckatv

Unofficial Kodi video add-on for Pecka.TV (Czech IPTV, platform 4NET.TV "LiveWeb").
Target: LibreELEC 12+ (Kodi 21 Omega+, Python 3) on Raspberry Pi 4. Communicate in Czech.

## Layout
- `plugin.video.peckatv/addon.xml` – manifest (pluginsource `default.py`, service `service.py`)
- `resources/lib/api.py` – HTTP client (urllib + LWPCookieJar, no external deps)
- `resources/lib/plugin.py` – router / directory listings / playback
- `resources/lib/iptv.py` – M3U + XMLTV export for PVR IPTV Simple Client
- `resources/lib/service.py` – periodic IPTV export
- `resources/lib/kodiutils.py` – settings, ListItem/inputstream.adaptive helpers
- `test/` – mock xbmc* modules + `run_test.py` (replays recorded API responses)

## API (https://online.pecka.tv/, all POST JSON, brand id 66)
- Session = cookie. Expired/unauthorized → HTTP 403 → re-authenticate.
- `api/authenticate` `{session_login_token}` (reliable; token = localStorage `sessionLoginToken` on online.pecka.tv)
  or `{login, password, id_brand:66}` (UNVERIFIED – Pecka hides login screen, real login goes via pecka.tv → `/autologin/<token>` → `api/authenticateByAutologinToken`).
  Response: `{success, authorized_device, session_token}`.
- `authorized_device:false` → `api/subscriber/pairBrowser {name}` → `pairing_success` (cookies identify the device, keep them).
- `api/device/getSubscriberProfiles/` → `remembered_subscriber_profile_id`; then `api/device/subscriberProfileUsed/` (every start).
- Device init after login (web: getDeviceToken → evaluateDeviceType `{payload:{user_agent,browser_features}}` → `device_type`
  → logDeviceStart `{firmware, device_type}` → getSettings `{id_subscriber_profile}`). Without it all EPG endpoints
  return HTTP 500 "Invalid url given: v2/epg/" (seen on a freshly paired Kodi; verified fixed in 0.1.5).
- `api/device/getSources` `{id_subscriber_profile}` → `channels[]` with
  `content_sources[0].stream_profile_urls.adaptive` = pre-signed HLS master (`_did,_sig,_ttl=86400`), `drm_config` null, `catchup_length` (hours), `id_epg`.
- `api/epg/getEpgByDate` `{epg_ids[], date:'YYYY-M-D' (web sends it unpadded; padding was not proven to matter), language[], timezone_offset(min)}` → `broadcasts{id_epg:[...]}`; includes previous evening.
- `api/epg/getCatchupBroadcasts` `{from,to,id_epg,language,timezone_offset}` – used by web (and us) for single-channel archive lists.
  ("Invalid url given: v2/epg/" was caused by missing device init, not by these params.)
- `api/contentdemon/getContent/` `{channel_id,start,end,broadcast_offset}` → `stream_uri, start_from, overlap_pre, overlap_post, drm_config, hls_playlist_type`.
  Verified via HAR: request `broadcast_offset:null`, response `start_from:60, overlap_pre:60, hls_playlist_type:VOD`.
  Kodi 22 ignores the `StartOffset` property (and a resume point) on resolved plugin URLs, so playback starts in the
  pre-roll. Intentionally left so – users like the minute before the programme; a seek-after-start was tried and dropped.
- Recordings (nPVR, web `RecordService`, feature flag `allow_pvrs`):
  `api/device/getAllPvrs {id_subscriber_profile}` → `pvrs[]` `{id,id_broadcast,id_channel,id_epg,name,channel_name,start,end,
  start_with_preoverlap,end_with_postoverlap,poster,photo,poster_address,locked,playable,date_expired,date_created}`;
  details via `api/epg/getBroadcasts {id_broadcasts[],language,timezone_offset}` → `broadcasts{id:…}`;
  delete `api/device/deletePvr {id,id_subscriber_profile}`;
  add `api/device/addPvr {id_subscriber_profile,id_broadcast,id_channel,id_epg,name[:64],start,end,poster,photo}`.
  Recordable (web `Channel.canBeBroadcastRecorded`): channel `pvr`; future → yes; running → channel `timeshift`;
  past → still inside `catchup_length`.
- Series (feature `allow_periodic_pvrs`, channel `periodic_pvr`): `api/device/getAllPeriodicPvrs` → `periodic_pvrs[]`
  `{id,id_show,id_channel,id_epg,name}`; `addPeriodicPvr {id_subscriber_profile,id_show,id_channel,name}`;
  `deletePeriodicPvr {id,id_subscriber_profile}`.
  Playback = same `getContent` as archive with the record's `id_channel,start,end` (web `getContentForRecord`).
- `api/peoplemeter/getStreamLimit/` → `{allow_stream,max_devices,current_devices}`.
- Logos: `https://epg.as.4net.tv/files/channel_logos/{id}.png`; programme images: replace `{size}` with `_300`.

## Open items
- Verify login/password auth for Pecka accounts.
- Verify recordings against a live account (built from web JS, not from a HAR).

## Workflow
- Test: `python3 test/run_test.py` (needs recorded responses in `test/fixtures/`, never commit real tokens).
- Build: `zip -r plugin.video.peckatv-<ver>.zip plugin.video.peckatv -x '*.pyc' '*__pycache__*'` (bump version in addon.xml).
- Deploy to Pi: copy folder to `/storage/.kodi/addons/plugin.video.peckatv/` (SSH root@<pi>, or SMB share `\\LIBREELEC\Userdata\..\addons`), then restart Kodi or `kodi-send --action="UpdateLocalAddons"`.
- Debug: `/storage/.kodi/temp/kodi.log`, grep `[plugin.video.peckatv]`.
