# Deployment

## 1. Push to GitHub

The repository is configured with the `eriquel04/hoffein-attorneys` GitHub remote.

```powershell
git add .
git commit -m "Prepare Render and Railway deployment"
git push origin main
```

The local `.env` file is ignored and must never be committed.

## 2. Create the Railway MySQL database

1. Create a Railway project.
2. Add a MySQL service.
3. Copy the MySQL connection values into the Render web service:
   - `MYSQLHOST` -> `DB_HOST`
   - `MYSQLPORT` -> `DB_PORT`
   - `MYSQLUSER` -> `DB_USER`
   - `MYSQLPASSWORD` -> `DB_PASSWORD`
   - `MYSQLDATABASE` -> `DB_NAME`
4. The first Render deploy runs `init_database.py`, which creates the schema from `schema.sql` and creates test accounts when their passwords are configured.

The application also reads Railway's `MYSQL*` names directly if the `DB_*` aliases are not set.

## 3. Create the Render web service

1. Select **New > Web Service** and connect `eriquel04/hoffein-attorneys`.
2. Use the `main` branch.
3. Render will use `render.yaml`, or configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python init_database.py && gunicorn --bind 0.0.0.0:$PORT app:app`
4. Add the secret environment variables listed in `.env.example`.
5. Set `DB_*` to the Railway MySQL values.
6. Use `/api/status` as the health check path.

## Important test notes

- Render's local filesystem is ephemeral. Uploaded documents in `uploads/` can be lost during redeploys or service restarts. Use object storage before production use.
- Update Google OAuth's authorized redirect URI to:
  `https://YOUR-RENDER-DOMAIN/auth/google/callback`
- Do not use the test accounts for real client information.
