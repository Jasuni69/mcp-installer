# API Reference — For Bridging Gaps

When the MCP tools don't cover a use case, make raw REST calls. All APIs authenticate via Azure CLI / DefaultAzureCredential.

## Authentication Scopes

| API | Base URL | Token Scope |
|-----|----------|-------------|
| Fabric REST | `https://api.fabric.microsoft.com/v1` | `https://api.fabric.microsoft.com/.default` |
| Power BI | `https://api.powerbi.com/v1.0/myorg` | `https://analysis.windows.net/powerbi/api/.default` |
| Microsoft Graph | `https://graph.microsoft.com/v1.0` | `https://graph.microsoft.com/.default` |
| OneLake ADLS Gen2 | `https://onelake.dfs.fabric.microsoft.com` | `https://storage.azure.com/.default` |
| SQL Endpoints | TDS/ODBC | `https://database.windows.net/.default` |

## Fabric REST API Endpoints

```
GET  /workspaces                                          — List workspaces
POST /workspaces                                          — Create workspace
GET  /workspaces/{id}/items                               — List items
GET  /workspaces/{id}/lakehouses                          — List lakehouses
POST /workspaces/{id}/lakehouses                          — Create lakehouse
GET  /workspaces/{id}/lakehouses/{id}/tables              — List tables
GET  /workspaces/{id}/warehouses                          — List warehouses
POST /workspaces/{id}/notebooks/{id}/getDefinition        — Get notebook (LRO)
POST /workspaces/{id}/semanticModels/{id}/getDefinition   — Get model def (LRO)
POST /workspaces/{id}/semanticModels/{id}/updateDefinition — Update model (LRO)
POST /workspaces/{id}/items/{id}/jobs/instances?jobType=X — Run job
GET  /workspaces/{id}/items/{id}/jobs/instances/{instId}  — Job status
```

## Power BI REST API Endpoints

```
POST /groups/{groupId}/datasets/{id}/executeQueries       — DAX query
     Body: {"queries": [{"query": "EVALUATE ..."}], "serializerSettings": {"includeNulls": true}}
POST /groups/{groupId}/datasets/{id}/refreshes            — Trigger refresh
GET  /groups/{groupId}/reports                            — List reports
POST /groups/{groupId}/reports/{id}/ExportTo              — Export report
```

## Microsoft Graph Endpoints

```
GET  /me                                                  — Current user
GET  /users/{email}                                       — User lookup
POST /me/sendMail                                         — Send email
POST /teams/{teamId}/channels/{channelId}/messages        — Teams message
GET  /me/drive/root/children                              — OneDrive files
```

## OneLake ADLS Gen2

```
Path format: /{workspaceName}/{lakehouseName}.Lakehouse/Files/{path}
             /{workspaceName}/{lakehouseName}.Lakehouse/Tables/{tableName}

GET    /?resource=filesystem&recursive=false               — List files
GET    /{path}                                             — Read file
PUT    /{path}                                             — Write file
DELETE /{path}                                             — Delete file
```

## Long-Running Operations (LRO) Pattern

Many Fabric APIs (getDefinition, updateDefinition, createItem) return 202 + Location header:
1. POST returns 202, headers include `Location` URL and `Retry-After` seconds
2. Poll GET on the Location URL until `status` is "Succeeded" or "Failed"
3. Result is in the response body of the final poll

## Python Code Patterns for Raw API Calls

**Get an Azure token:**
```python
from azure.identity import DefaultAzureCredential
cred = DefaultAzureCredential()
token = cred.get_token("https://api.fabric.microsoft.com/.default").token
headers = {"Authorization": f"Bearer {token}"}
```

**Make a Fabric API call:**
```python
import requests
resp = requests.get("https://api.fabric.microsoft.com/v1/workspaces", headers=headers)
workspaces = resp.json()["value"]
```

**Handle LRO:**
```python
import time
resp = requests.post(url, headers=headers, json=body)
if resp.status_code == 202:
    location = resp.headers["Location"]
    retry_after = int(resp.headers.get("Retry-After", 5))
    while True:
        time.sleep(retry_after)
        poll = requests.get(location, headers=headers)
        status = poll.json().get("status")
        if status in ("Succeeded", "Failed"):
            break
```

**Execute DAX via Power BI API:**
```python
token = cred.get_token("https://analysis.windows.net/powerbi/api/.default").token
resp = requests.post(
    f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
)
```

**SQL via ODBC:**
```python
import pyodbc
token = cred.get_token("https://database.windows.net/.default").token
conn = pyodbc.connect(
    f"Driver={{ODBC Driver 18 for SQL Server}};"
    f"Server={endpoint}.datawarehouse.fabric.microsoft.com;"
    f"Database={database};"
    f"Encrypt=Yes;TrustServerCertificate=No",
    attrs_before={1256: token}  # SQL_COPT_SS_ACCESS_TOKEN
)
```
