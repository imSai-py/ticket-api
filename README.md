# ticket-api

A small service that serves support ticket data and a summary, plus a simple web page.

Requires Python 3.8 or newer.

## Setup & Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

3. Open the application:
   - Web interface: http://localhost:8000/
   - Interactive API docs (Swagger): http://localhost:8000/docs
   - OpenAPI schema: http://localhost:8000/openapi.json

## Configuration

The service supports the following environment variable:
- `TICKETS_DATA_PATH`: Optional path to the ticket CSV dataset. Defaults to `data/tickets_sample.csv`.

## Testing

Run tests with pytest:
```bash
pytest
```
Or run the unified verification script:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1
```
