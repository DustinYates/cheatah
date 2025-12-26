# Creating Tenant in Production Database

The production database uses Cloud SQL with a Unix socket connection that only works from within GCP or with the Cloud SQL Proxy.

## Option 1: Use Cloud SQL Proxy (Recommended)

If you have the Cloud SQL Proxy set up:

```bash
./scripts/create_tenant_production_with_proxy.sh \
    --name "Fake Swim School" \
    --subdomain "fake-swim-school" \
    --email "dustin.yates@gmail.com" \
    --password "Hudlink2168"
```

**Prerequisites:**
- Cloud SQL Proxy binary in the project root (download from: https://cloud.google.com/sql/docs/postgres/connect-admin-proxy#install)
- Or install via: `gcloud components install cloud-sql-proxy`

## Option 2: Use Production API Directly

Since you can't easily connect to the production database locally, the easiest way is to:

1. **Use the production API to create the tenant via the admin endpoint**

   First, get a global admin JWT token by logging in as a global admin:
   
   ```bash
   curl -X POST "https://chattercheatah-900139201687.us-central1.run.app/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@chattercheetah.com","password":"your-admin-password"}'
   ```

   Then use that token to create the tenant:
   
   ```bash
   curl -X POST "https://chattercheatah-900139201687.us-central1.run.app/api/v1/admin/tenants" \
     -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Fake Swim School",
       "subdomain": "fake-swim-school",
       "is_active": true
     }'
   ```

   Then create the admin user:
   
   ```bash
   curl -X POST "https://chattercheatah-900139201687.us-central1.run.app/api/v1/users" \
     -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN" \
     -H "X-Tenant-Id: 6" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "dustin.yates@gmail.com",
       "password": "Hudlink2168",
       "role": "tenant_admin"
     }'
   ```

## Option 3: Connect via Cloud Shell

1. Open Google Cloud Shell
2. Clone the repository
3. Set up the environment
4. Run the add_tenant.py script directly with the DATABASE_URL environment variable set

