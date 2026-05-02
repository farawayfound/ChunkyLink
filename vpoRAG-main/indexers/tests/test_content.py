# -*- coding: utf-8 -*-
"""
Shared test content for both JSON and Markdown indexer tests
Based on actual VPO (Video Product Operations) knowledge base
"""

# Test content based on actual VPO knowledge base
TEST_QUERIES = """
Creating CEITEAM Tickets for Entitlements Support

Issue Type: INC/SCI Entitlements Support
Will be assigned to: Jo Shumaker
Related Issues:
- Entitlement Packages in ACE
- Provisioning (Billing Codes & BOCs) in ACE
- Service Levels in Workflow/CLMS
- Billing Codes in Workflow/CLMS
- DAC/EC Packages

Requested Information:
- Overview of issue
- Link to Triage/Master JIRA Ticket
- Controller & Map
- CLM/CLU Name
- Service Name
- Channel Number
- Service Level/Package Name
"""

TEST_SOP = """
Engage a NetOps fix agent for Issue Resolution via INC

Process for escalating multiple customer impact issues:
1. This process is used for ALL multi-customer impacting issues that require a NetOps fix agent
2. Existing WebEx Teams rooms can be leveraged for notification and awareness
3. INCs should be generated for tracking and resolution

NOC Contact Information:
- NOC Regional Map: http://142.136.228.98/
- Phone: 866-248-7662

Creating the Remedy ticket:
1. Log into SWAT https://nocworkflow-prd.corp.chartercom.com/swat/createincident
2. Go to Incident Management → New Incident
3. Fill out required fields
"""

TEST_MANUAL = """
Video Operations Engagement (VPO)

IPVC Production Issues/Outages ACE / CLMS Changes TMC Support MindControl

1. Notify IPVC of the impacting issue via the proper teams room
2. Create JIRA ticket:
   - Project: VOINTAKE
   - Issue Type = Intake Request
   - Summary = high level sentence on the issue
   - Request type = IPVC Production Support
   - Category = N/A
   - Project Objective = Summary of the reported issue
   - Project Background = Multi-customer impacting issue requiring IPVC support
   - VP Name – Kirk White
"""

TEST_TROUBLESHOOTING = """
Troubleshooting APEX3000 Fan Alarms

Issue: APEX3000 Fan Alarms in multiple Maine locations
Locations affected:
- Rumford, Maine
- Dover, Maine
- Bucksport, Maine
- Calais, Maine
- Bangor, Maine

Resolution steps:
1. Create VOINTAKE ticket
2. Engage VSC Support to verify Circuits
3. Check for BB Optical Span Loss
4. Monitor fan status
"""

TEST_REFERENCE = """
TMS Ticket for CSG & ICOMS

TMS ticket is needed for Billing Interface team to:
- Verify that the billing system is sending the authorizations for the packages
- BIS related investigations

Use this link to create the ticket: TMS Interface Ticket Entry .docx

When STBs not registered in DAC:
- Create a TMS ticket with account details
- Category 1: CSG
- Category 2: Interface/Port
- Description: Check for potential BSI mismatch or lost loop
"""

TEST_CSV_CONTENT = """Issue_Type,Assigned_To,Related_Issues,Status,Summary,Description
INC/SCI Entitlements Support,Jo Shumaker,Entitlement Packages in ACE,Open,ACE entitlement issue,Ticket for ACE entitlement support investigation
INC/SCI IP Support,Peter Roach,Services in ACE,In Progress,ACE service ticket,Support ticket for ACE services and CLMS billing codes
INC/SCI TVE Support,Ignacio Velasco,TVE/3rd Party App Authentication,Open,TVE support issue,Ticket for TVE authentication and entitlement support
INC/SCI CLM Support,Jo Shumaker,Channel Positions,Resolved,CLMS channel ticket,Support ticket for CLMS channel position and ACE package issue
"""

# Common VPO tags for cross-category testing
COMMON_VPO_TAGS = ['ace', 'ticket', 'issue', 'ipvc', 'clms', 'inc', 'entitlements', 'support']
