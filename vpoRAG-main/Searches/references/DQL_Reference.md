# DQL Query Reference - OpenSearch Quantum Events

> **Scope:** OpenSearch DQL only. DQL syntax (`field.path: value`, dot-notation) is INVALID in Splunk and VO Kibana.
> - `index=aws*`, `| stats`, `| rex` are **Splunk SPL** — do NOT use in DQL queries
> - `"OV-TUNE-FAIL" AND location:kma` is **VO Kibana** — do NOT use in DQL queries
> - STB/WorldBox tune failures / EPG → use **Kibana_Reference.md** (VO Kibana)
> - API logs, entitlements, lineup service → use **SPL_Reference.md** (Splunk)

## Core Syntax

**Field Search**: `field_name: search_term`
**Phrase Search**: `field_name: "exact phrase"`
**Multiple Terms**: `field_name: (term1 OR term2)`
**Field Existence**: `field_name:*`
**Wildcards**: `field_name: term*` (only `*` supported, not `?`)
**Nested Fields**: `state.content.stream: {playbackType: dvr AND cdvrType: recorded}`
**Escape Characters**: Use `\` before `\ ( ) : < > " *`

## Boolean Operators

`AND` / `OR` / `NOT` (uppercase preferred) | Grouping: `(field1: v1 OR field2: v2) AND field3: v3`

## Ranges

**Numeric**: `field >= 100 AND field <= 300`
**Epoch ms**: `receivedTimestamp >= 1762712587795 AND receivedTimestamp < 1762882965085`
**Date String**: `message.timestamp >= "2025-11-01" AND message.timestamp < "2025-11-30"`
**Exists + Not Equal**: `field:* AND NOT field: value`

## Quantum Event Schema

### Top-Level
- `receivedTimestamp` - Epoch ms (numeric)
- `customer` - "Charter" | `domain` - "video" | `partition` - encrypted billing ID

### Message
- `message.name` - "error", "playbackFailureBeforeRetry", "webSocketError"
- `message.category` - "error", "playback", "networkTransaction"
- `message.timestamp` - ISO 8601 string
- `message.triggeredBy` - "application", "analytics"
- `message.sequenceNumber` (numeric) | `message.timeSinceLastEventMs` (numeric)
- `message.eventCaseId`

### Application Error
- `application.error.errorCode` - "AN-2500", "AN-2706", "RLP-1999", "RCD-1006", "RGE-1003", "1006", "1008"
- `application.error.errorMessage` (text) | `application.error.errorType` - "analytics", "playbackRestartAttempt", "webSocket", "nonFatalApplicationError"
- `application.error.clientErrorCode` | `application.error.analyticsImpact` - "error", "warning"

### State
- `state.name` - "playing", "paused", "buffering", "failed", "initiating", "navigating"
- `state.previousState.name` | `state.entryTimestamp` (numeric)
- `state.currentVideoPosition` (seconds) | `state.entryVideoPosition` (seconds)

### Content Stream
- `state.content.stream.playbackType` - "dvr", "linear", "vod"
- `state.content.stream.cdvrType` - "recorded", "inProgress"
- `state.content.stream.cdn` - "cDVR_NextGen", "Akamai"
- `state.content.stream.streamHost` | `state.content.stream.programmerCallSign`
- `state.content.stream.streamingFormat` - "dash" | `state.content.stream.drmType` - "widevine"
- `state.content.stream.recordingStartTimestamp` / `recordingStopTimestamp` (numeric)

### Content Classification
- `state.content.contentClass` - "cdvr", "linear", "vod"
- `state.content.contentFormat` - "SD", "HD"
- `state.content.identifiers.dvrRecordingId` | `tmsGuideId` | `tmsProgramId`

### Playback
- `state.playback.playbackSelectedTimestamp` / `playbackStartedTimestamp` (numeric)
- `state.playback.tuneTimeMs` (numeric) | `state.playback.playerSessionId`
- `state.playback.retriedErrorCode` | `state.playback.retryCategory` - "brokenStream"
- `state.playback.pauseLiveTvIsEnabled` | `state.playback.daiEnabled`

### View/Page
- `state.view.currentPage.pageName` - "playerOnDemand", "playerLiveTv", "myLibrary", "login"
- `state.view.currentPage.appSection` - "myLibrary", "guide", "home", "preAuthentication"
- `state.view.previousPage.pageName`

### Visit/Session
- `visit.visitId` | `visit.appSessionId`
- `visit.applicationDetails.appVersion` | `visit.applicationDetails.applicationType` - "Roku"
- `visit.applicationDetails.venonaVersion`
- `visit.device.model` | `visit.device.operatingSystem`
- `visit.connection.networkStatus` - "onNet", "offNet" | `visit.connection.connectionType` - "wifi"
- `visit.videoZone.division` | `visit.videoZone.lineup`
- `visit.account.videoPackage` | `visit.account.details.mso` - "TWC"

### API & Operation
- `application.api.apiName` | `application.api.host` | `application.api.path` | `application.api.responseTimeMs`
- `operation.success` (boolean as string) | `operation.additionalInformation`

## Common Use Cases

**cDVR Playback Failure Analysis (cross-data-center)**
```
visit.applicationDetails.applicationType:* AND
visit.applicationDetails.applicationName:(OneApp OR BulkMDU) AND
state.content.stream.playbackType:dvr AND
operation.success:false AND
NOT state.previousState.name:initiating
```
*Use: Broad cDVR failure sweep. Filter by `visit.videoZone.division` to narrow to a market.*

---

## Query Examples

**DVR Playback Errors**
```
state.content.stream.playbackType: dvr AND
application.error.errorCode: ("AN-2500" OR "AN-2706" OR "RLP-1999") AND
message.timestamp >= "2025-11-01"
```

**In-Progress Recording Playback**
```
state.content.stream.cdvrType: "inProgress" AND
state.content.stream.playbackType: dvr AND
application.error.errorType: analytics AND
message.timestamp >= "2025-11-01"
```

**WebSocket Failures**
```
application.error.errorType: webSocket AND
application.error.errorCode: ("1006" OR "1008") AND
application.api.host: "client-notifications.vpns.spectrum.net"
```

**State Machine Issues**
```
state.previousState.name: playing AND state.name: paused AND
message.timeSinceLastEventMs < 1000 AND
application.error.errorCode: "AN-2500"
```

**Playback Restart Attempts**
```
application.error.errorType: playbackRestartAttempt AND
state.playback.retriedErrorCode: * AND
state.playback.retryCategory: "brokenStream"
```

**Failed Instant Resume**
```
application.error.errorCode: "RGE-1003" AND
application.error.errorMessage: "Instant Resume Page Failure" AND
operation.success: "false"
```

**CDN/Stream Host Analysis**
```
state.content.stream.cdn: "cDVR_NextGen" AND
state.content.stream.streamHost: *cdvr.spectrum.com AND
application.error.errorCode: *
```

**Roku Device Issues**
```
visit.device.model: "3820X2" AND
visit.applicationDetails.appVersion: "15.6.1" AND
application.error.errorCode: * AND
state.content.stream.playbackType: dvr
```

**Specific Channel/Content**
```
state.content.stream.programmerCallSign: "NEWSNTN" AND
state.content.contentClass: cdvr AND
application.error.errorCode: * AND
message.timestamp >= "2025-11-01"
```

**Account/Division Specific**
```
visit.videoZone.division: "CLE" AND visit.videoZone.lineup: "445" AND
visit.account.videoPackage: "SPP Select" AND
application.error.errorCode: *
```

**Completed DVR Recordings Only**
```
state.content.stream.playbackType: dvr AND
state.content.stream.cdvrType: "recorded" AND
NOT state.content.stream.cdvrType: "inProgress"
```

**Exclude Test Traffic**
```
visit.connection.networkStatus: "onNet" AND visit.account.details.mso: "TWC"
```

## Anti-Patterns

❌ `field:value1 OR value2` → ✅ `field: (value1 OR value2)`
❌ `field >= 100 and <= 300` → ✅ `field >= 100 AND field <= 300`
❌ `field: wind?` → ✅ `field: wind*` (no `?` in DQL)
❌ `state.content.stream.playbackType: "dvr"` → ✅ `state.content.stream.playbackType: dvr` (no quotes for single keywords)
❌ `message.timestamp >= 1762712587795` → ✅ `receivedTimestamp >= 1762712587795` (epoch uses receivedTimestamp)
❌ `operation.success: true` → ✅ `operation.success: "true"` (boolean as string)
❌ `errorCode: AN-2500` → ✅ `application.error.errorCode: "AN-2500"` (full path, quote hyphenated)
