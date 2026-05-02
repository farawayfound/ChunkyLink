# SPL Query Reference - Splunk

> **Scope:** Splunk only. SPL syntax (`index=`, `| stats`, `| rex`, `| table`) is INVALID in VO Kibana and OpenSearch DQL.
> - STB tune failures / EPG errors / reboots → use **Kibana_Reference.md** (VO Kibana)
> - STVA/OneApp/Roku client playback errors → use **DQL_Reference.md** (OpenSearch)
> - API logs, entitlements, lineup service, account data → **this file**

## Core Syntax

**Index**: `index=index_name` | **Source**: `source="*pattern*"` | **Sourcetype**: `sourcetype="kube:container:name"`
**Field**: `fieldName=value` | **Wildcard**: `field=*pattern*` | **Time**: `earliest=-30d latest=now`
**AND**: implicit (space) or `AND` | **OR**: `field1=v1 OR field2=v2` | **NOT**: `NOT field=value` or `field!=value`

## Indexes

| Index | Service |
|-------|---------|
| `index=aws-effie` | Effie (DTC, consumer, notifications) |
| `index=aws-stva` | STVA streaming services |
| `index=aws-spec` | Spectrum (LRMMiddle, entitlements, stblookup) |
| `index=aws-sidecar` | Equipment domain services |
| `index=aws-cdvr` | Cloud DVR |
| `index=aws-tve` | TV Everywhere |
| `index=aws-shared` | Shared services (federated auth) |
| `index=aws-PINXT-prod*` | PINXT (location, password reset) |
| `index=app_mda` | MDA order/subscription events |
| `index=app_spc` | SPC account services |

## Key Sources & Sourcetypes

```
source="*directtocustomer*"     # DTC partner activations
source="*dtcconsumer*"          # DTC consumer events
source="*dtcnbcservice*"        # Peacock/NBC DTC
source="*lrmmiddle*"            # LRM entitlements
source="*equipment-domain-service*"
source="*stblookup*"            # STB lineup lookup
source="*stb*"                  # Set-top box
source="*ascu.log"              # MDA orders (host=vm0p*)
sourcetype=kube:container:bg-cdvr-prod-cdvrspecflow
```

## Important Fields

**Account**: `accountNumber`, `accountId`, `acpAccountNumber`, `txnBlngAccountNumber`, `billingAccountIdMaster`, `billingAccountIdTenant`
**Session/Tx**: `txnId`, `traceid`, `traceId`, `requestId`, `visitId`, `playerSessionId`, `orderNumber`
**Auth**: `clientIp`, `sourceApplication`, `statusCode`, `subStatusResponse`, `classification`, `auth_method`
**Location**: `behindOwnModem`, `inMarket`, `inUS`, `mapTEnabled`
**Entitlement**: `pricingPlanName`, `productName`, `productStatus`, `subscriptionStatus`, `entitlementId`, `partnerId`, `partnerCustomerId`
**API**: `methodPath`, `servicePath`, `status`, `exitReason`, `errorCode`, `errorMessage`
**Lineup**: `lineupId`, `lineup_id`, `channelLineupId`, `lineup_flow`

## SPL Commands

**Filter**: `search`, `where`, `dedup`
**Extract**: `rex field=_raw "pattern=(?<name>value)"`, `spath path=field output=alias`
**Manipulate**: `eval`, `fillnull value="N/A" f1 f2`, `rename old as new`, `fields`
**Aggregate**: `stats count by f1,f2`, `eventstats`, `timechart span=1d count by field`
**Output**: `sort -_time`, `head 100`, `table _time, f1, f2`

## Rex Patterns

```splunk
rex field=_raw "accountNumber=(?<accountNum>\d+)"
rex field=_raw "acpAccountNumber\":\"(?<ACP_ACCOUNT_NUMBER>\d+)"
rex field=_raw "txnId=(?<txnId>[^,\s]+)"
rex field=_raw "(?<Trace_ID>[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12})"
rex field=_raw "pricingPlanName=(?<plan>[^=]+)(?=, \w+=)"
rex field=_raw "productName\":\"(?<PRODUCT_NAME>[^\"]+)\""
rex field=_raw "status\":\"(?<status>\w+)"
rex field=_raw "errorCode\":\"(?<errorCode>[^\"]+)"
rex field=_raw "IPDomainService - requestIp\=\[(?<BTM_IPv4>[\d\.]+)\] Response: \[macAddress\=(?<MacAddr>[A-Z0-9a-z]+) accountNumber=(?<BTM_AccNum>[A-Z0-9\/\.a-z]+)"
rex "ConnectionStatus for model: (?<model>(?s).+) returning"
rex "returning as: (?<connectionState>(?s).+) resolved"
rex "decision\"\:\ \n\n\"(?<DECISION>.+?)\""
rex "resourceID\"\:\"\(?<resourceChannel>.+?)\""
```

## Query Catalog

### Account & Service Lookup

**Bulk WiFi Type (MDU)**
```splunk
index=* ACCOUNT_NUMBER getcurrentservicesresponse index=app_spc
| rex "(?<BulkWIFIType>\"bulkWifiType\" : \"(?<PropertyType>.+?)\"),"
| rex "\"divisionID\" : \"(?<DIV>[A-Z0-9\.]+)\""
| rex "\"accountNumber\" : \"(?<AccNum>\d+)\""
| eval FullAcc=DIV + "/" + AccNum
| stats count by FullAcc,BulkWIFIType,PropertyType
```
*Use: Verify bulk WiFi provisioning for MDU accounts. Extracts division, account, WiFi type (Managed/Non-Managed)*

**Identity Domain Service**
```splunk
index=aws* ACCOUNT_NUMBER methodPath="/identitydomainservice/identity/v3/identity/query-account-identity:POST" "*Response Status Code & Response Content*"
```

### Authentication & Network Position

**Auto-Access (Behind-Modem Auth)**
```splunk
index=aws-* autoaccessresponse* "CLIENT_IP"
| table _time, txnId, clientIP, sourceApplication, statusCode, subStatusResponse, classification, billingAccountIdMaster, accountType, billingAccountIdTenant, statusReason, subStatusReason
| sort -_time
```
*Use: Troubleshoot automatic login failures when customer is behind Spectrum modem*

**Location API (BTM/In-Market/In-US)**
```splunk
index=aws* ACCOUNT_NUMBER */pinxt/customer/location/v1* *deaee*
| table _time, traceId, billing_acct, classification, client_id, clientIp, mapTEnabled, auth_method, behindOwnModem, inUS, inMarket
```
*Key fields: `behindOwnModem`, `inMarket`, `inUS`, `mapTEnabled` (MAP-T IPv6 transition)*

**Login vs BTM Account Mismatch**
```splunk
ACCOUNT_NUMBER index=aws-shared serviceName=unified-federatedauthn-middle* "IPDomainService - requestIp" (*stva* OR *oneapp*)
| rex "IPDomainService - requestIp\=\[(?<BTM_IPv4>[\d\.]+)\] Response: \[macAddress\=(?<MacAddr>[A-Z0-9a-z]+) accountNumber=(?<BTM_AccNum>[A-Z0-9\/\.a-z]+)"
| eval Date=strftime(_time,"%F")
| rename accountNumber AS LoginAccountNumber
| fillnull value="N/A" sourceApplication,clientIp,LoginAccountNumber,BTM_IPv4,MacAddr,BTM_AccNum
| stats values(Date) by sourceApplication,clientIp,LoginAccountNumber,BTM_IPv4,MacAddr,BTM_AccNum
```
*Use: Resolve "Login account and QABIP account don't match" errors*

### Lineup & Entitlements

**Lineup ID - CHTR**
```splunk
index=aws-stva ACCOUNT_NUMBER methodPath="GET:/lineupidservice/lineup"
| table _time, traceId, clientName, accountNumber, clientIp, lineup_flow, lineup_id, lineupId
| sort -_time
```

**Lineup ID - TWC/BHN**
```splunk
index=aws-stva ACCOUNT_NUMBER app=lantern-foc-lids
| spath "data.Item.data.body"
| search "data.Item.data.body"="{\"lineupId\":LINEUP_ID,\"market\":\"MARKET\",\"national\":false,\"cacheable\":true}"
| table data.Item.data.body
```

**STB Lineup Lookup by Region/Hub**
```splunk
index=aws-spec source="*stblookup*" "{\"region\":\"REGION\",\"hub\":\"HUB\"}"
| spath input=responseJson output=lineupId path=lineupId
| stats count by lineupId
```

**STB Lineup by Account + MAC**
```splunk
index=aws-* host=prd* source=*stb* "ACCOUNT_NUMBER" MAC_ADDRESS channelLineupId
```

**Lineup Service Errors**
```splunk
index=aws-stva methodPath=GET:/lineupidproxy/v1/lineupid/videotopology "LINEUPIDSERVICE 404 LineupId not found for given accountNumber [*] and headendId [11]"
| timechart span=1h count
```

**Streaming Device Lineup**
```splunk
index=aws-stva ACCOUNT_NUMBER api/smarttv/lineup/v1*
| table _time, requestId, accountId, app, clientIp, clientSource, clientType, deviceId, responseContent
```
*Logic: CHTR=system print+headend, TWC/BHN=ZIP code mapping, Boxed=depends on STB type*

**Entitlements (LRM)**
```splunk
index=aws-* methodPath="/services/v2/entitlements:GET" application="/lrmmiddle/" ACCOUNT_NUMBER
```

```splunk
index=aws-spec host=prd* source=*lrmmiddle* "methodpath=/services/v2/entitlements" ACCOUNT_NUMBER
earliest=-30d
| rex field=_raw "billingcodes=(?<billingCodes>[^&\s]+)"
| table _time, billingCodes, status
| head 100
```

### Streaming & Playback

**Live Stream Fetch**
```splunk
index=* ACCOUNT_NUMBER /api/smarttv/stream/live/v4/* "TRACE_ID"
| table _time, traceId, clientIp, clientType, deviceId, app, requestPath, responseStatus, responseFailure, responseContent
```
*CDN patterns: `linear.stvacdn.spectrum.com` (non-DAI), `edge-mm.spectrum.net` (DAI via MDC), `linear-novi.stvacdn` (OOT)*

**User Capabilities**
```splunk
index=aws* ACCOUNT_NUMBER api/smarttv/user/capabilities/v3 *cdvr*
| table _time, requestId, traceId, accountId, app, clientIp, clientType, deviceId, responseBody, responseContent
```
*Features: cDVR, OTA, TVOD, Watch On Demand, Instant Upgrade*

**OTA Capability (Samsung TV)**
```splunk
index=aws-stva* app=IPVS requestPath="/api/smarttv/user/capabilities/v3" clientType="*samtv*" responseContent="*\"ota\":{\"authorized\":true*"
| timechart dc(accountId)
```

**Buyflow / Current Packages**
```splunk
index=aws* "/buyflow/v5/currentEntitlementPackages" ACCOUNT_NUMBER *oneapp-ovp*
| dedup txnId
| table _time, account, clientType, clientIp, responseJson, classification
```

**Instant Upgrade (STB)**
```splunk
index=aws* ACCOUNT_NUMBER IUMiddle* "*Successfully purchased productId*"
| table _time, application, mac, message
```

### cDVR (Cloud DVR)

**Partial Recordings by Market**
```splunk
index=aws-cdvr host!="ipvc-cdvr-v121.ipvideo.stg.*" sourcetype=kube:container:bg-cdvr-prod-cdvrspecflow "Partially Completed" AND log-message.http-body.status.description!=NULL
| table log-message.http-body.status.description, log-message.http-body.status.state, log-message.http-body.subscriber.market
| stats count by log-message.http-body.subscriber.market
```

**Recording Details / Lifecycle**
```splunk
index=aws-cdvr "ACCOUNT_NUMBER" "SHOW_TITLE"
| spath path=log-message.http-body.title output=title
| spath path=log-message.http-body.programId output=programId
```

### DTC Partner Integrations

**Disney+/Hulu/ESPN+/Peacock Activation**
```splunk
index=aws-effie source="*directtocustomer*" "Successfully notified Disney of the product" AND ACCOUNT_NUMBER
```
*Flow: CSG → Effie (DTC) for regular activations; Charter Kinesis → MDA → DTC for upgrades*

**Peacock Subscription Lifecycle (Boku)**
```splunk
index=aws-effie source="*dtcnbcservice*" "c.c.d.n.s.AbstractCallbackService - Boku API Callback" partnerCustomerId=PARTNER_CUSTOMER_ID
| table partnerCustomerId, consumerIdentity, entitlementId, bundleStartsAt, offerName, product, cancelReason, error
```

**DTC Consumer Subscription**
```splunk
index="aws-effie" source="*dtcconsumer*" sourcetype="kube:container:dtcconsumer"
ACCOUNT_NUMBER "Subscription Event Processing"
earliest=-30d
| rex field=_raw "pricingPlanName=(?<plan>[^=]+)(?=, \w+=)"
| rex field=_raw "subscriptionStatus=(?<status>[^\s,]+)"
| table _time, plan, status
| head 50
```

**Streaming Usage (DirectToCustomer)**
```splunk
index=aws-effie source="*directtocustomer*" ACCOUNT_NUMBER (partnerId OR entitlementId)
earliest=-30d
| rex field=_raw "partnerId=(?<partnerId>[^\s,]+)"
| rex field=_raw "entitlementId=(?<entitlementId>[^\s,]+)"
| table _time, partnerId, entitlementId
| head 50
```

### TVE (TV Everywhere)

**TVE Authorization Decisions**
```splunk
index=aws-tve "PARTNER_NAME" "AuthZ RESPONSE" ("GUID" OR "email@domain.com" OR "ACCOUNT_NUMBER")
| transaction keepevicted=true by txnId
| rex "decision\"\:\ \n\n\"(?<DECISION>.+?)\""
| rex "resourceID\"\:\"\(?<resourceChannel>.+?)\""
| stats count by dateee, DECISION, resourceChannel
```
*Partners: Paramount+, Max, Disney apps. Key: DECISION (Permit/Deny), resourceChannel*

### Equipment & Devices

**STB Connection State**
```splunk
index=aws-sidecar host=*prd* source=*equipment-domain-service* ACCOUNT_NUMBER
methodPath="/equipment/v4/equipment/{equipmentId}/connection-state:GET"
earliest=-7d
| rex "ConnectionStatus for model: (?<model>(?s).+) returning"
| rex "returning as: (?<connectionState>(?s).+) resolved"
| stats count by _time, model, connectionState, status
| sort +_time
| head 100
```

**Device Inventory**
```splunk
index=* ACCOUNT_NUMBER /spp/v1/accounts/DIV.ACCT:ACCOUNT_NUMBER/devices
| table _time, requestId, clientType, clientIp, responseContent
```

### Troubleshooting & Diagnostics

### 3802 / Channel Unavailable (Spectrum Guide — STB)

**STB Tune Failure — Get Failed Reason by MAC**
```splunk
index=aws-spec host=prd* source=*stblookup* "MAC_ADDRESS" earliest=-7d
| dedup txnId
| table _time, txnId, lineupId, controllerId, controllerName, failReason, tuneResult
| sort -_time | head 50
```
*Use: First step for 3802. Confirms what lineup was pulled and surfaces failReason (STREAM-NO-DATA, STREAM-NO-PMT, SDV-INV-SG, etc.)*

**3802 Tune Error Reason — Navigator/SGUI**
```splunk
index=aws* host=prd* (source=*navigator* OR source=*sgui*) "MAC_ADDRESS" "3802" earliest=-14d
| rex field=_raw "reason=(?<tune_reason>[A-Z\-]+)"
| stats count by tune_reason
| sort -count
```
*Use: Identify the specific 3802 error code driving the issue. Determines TC vs SCI vs OPS-Z path.*

**Streaming Tuning Errors — AMS (Targeted by MAC + Channel)**
```splunk
index=spec-zod-ams-am* "MAC_ADDRESS" (Reason:"CARR-FRQ-UNAV" OR Reason:"STREAM-NO-DATA" OR Reason:"STREAM-NO-PAT" OR Reason:"STREAM-NO-PMT" OR Reason:"SDV-BW-NA" OR Reason:"CAS-CHANNEL-NOT-AUTHORIZED") earliest=-7d
| stats count by Reason, channel
| sort -count
```
*Use: Confirm stream-level failure reason. If count is high across multiple accounts → area/headend issue, create INC.*

**STB Lineup Mismatch — ServicesLineupZdbSourcecommit**
```splunk
index=aws-spec host=prd* source=*stblookup* "MAC_ADDRESS" "ServicesLineupZdbSourcecommit" earliest=-7d
| table _time, _raw
| sort -_time | head 20
```
*Use: If services version ≠ applied lineup version → box cached wrong lineup. Contact OPS-Z to republish lineup for temp fix.*

**Error code → action mapping:**

| Error Code | Cause | Action |
|---|---|---|
| STREAM-NO-DATA | Stream has no data | TC — check headend feed |
| STREAM-NO-PMT | PMT missing in stream | TC — POSTTRIAGE-26966 |
| STREAM-NO-PAT | PAT missing in stream | TC — POSTTRIAGE-27180 |
| CARR-FRQ-UNAV | Carrier frequency not presented | TC — POSTTRIAGE-27198 |
| SDV-INV-SG | Invalid SDV service group ID | SCI — POSTTRIAGE-27197 |
| SDV-BW-NA | SDV server bandwidth exhausted | SCI — POSTTRIAGE-27202 |
| CAS-CHANNEL-NOT-AUTHORIZED | CAS has no keys for channel | SCI — POSTTRIAGE-27193 |

**Error Analysis**
```splunk
index=aws-* ACCOUNT_NUMBER (error OR fail OR exception)
earliest=-7d
| rex field=_raw "errorCode[\"=:](?<errorCode>[^\",\s]+)"
| rex field=_raw "errorMessage[\"=:](?<errorMessage>[^\"]+)"
| stats count by errorCode, errorMessage
| sort -count
```

**Caller ID Logs**
```splunk
index=aws-spec source="/logs/callerid-sip.out" "incoming request"
| timechart span=1d count by host limit=70
```

**Password Reset Volume**
```splunk
index=aws-PINXT-prod* "Consumer_password_reset*"
| timechart span=1m count
```

**Lantern Upstream Routing**
```splunk
index=aws-stva app="lantern-lrs" messageType=api requestUrl=*api/smarttv/channels/v3* accountId=ACCOUNT_ID
| table _time, accountId, lanternSource, requestUrl, traceId
```
*Use: Determine if request was handled by proxy vs. deep call*

### MDA Orders/Subscriptions

```splunk
index=app_mda host="vm0p*" source=*ascu.log ACCOUNT_NUMBER
("Enriched Json Msg:" OR "EnfMessageResult:")
earliest=-30d
| rex field=_raw "pricingPlanName\":\"(?<PRODUCT_NAME>[^\"]+)\""
| rex field=_raw "orderStatus\":\"(?<ORDER_STATUS>\w+)"
| table _time, PRODUCT_NAME, ORDER_STATUS
| head 100
```

## Best Practices

❌ `index=aws-* accountNumber` → ✅ `index=aws-effie accountNumber` (specific index)
❌ `source=directtocustomer` → ✅ `source="*directtocustomer*"` (wildcards)
❌ `earliest=-30d | head 100 | rex ...` → ✅ `earliest=-30d | rex ... | head 100` (extract then limit)
❌ `rex "accountNumber=(\d+)"` → ✅ `rex "accountNumber=(?<accountNum>\d+)"` (named capture)
❌ `index=aws-effie | search accountNumber` → ✅ `index=aws-effie accountNumber` (filter in base)

**Always:** specify index, use `earliest=`, extract with `rex` before `head`, use `table` for output, `sort -_time` for chronological
**Dedup:** `| dedup txnId` for transaction-based queries
**Exclude noise:** `NOT source="*effienotificationservice*"` | `NOT source="*order-history-kafka-daemon*"`

## Time Range Syntax

`earliest=-30d` | `earliest=-7d` | `earliest=-24h` | `earliest=@d` (midnight) | `earliest="2025-01-01" latest="2025-01-31"`
