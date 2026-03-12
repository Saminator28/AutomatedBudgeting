# Automated Budgeting

> **Upload your bank statements. Get an instant financial dashboard. Everything runs on your own computer — your data never leaves.**

---

## What Is This?

Automated Budgeting reads your bank and credit card statement PDFs and turns them into a clean, interactive dashboard where you can see exactly where your money is going — without any spreadsheets, subscriptions, or accounts.

If you've ever looked at your bank statement and thought *"where did all my money go this month?"* — this is for you.

**What you get:**
- A web dashboard showing your spending by category (groceries, dining, gas, etc.)
- Separate breakdowns for income and expenses
- Charts tracking your spending month over month
- An AI chatbot that answers questions like "how much did I spend on dining last month?"
- The ability to upload statements, edit transactions, and re-categorize anything

**Who is it for?** Anyone who downloads PDF statements from their bank and wants a clear picture of their finances without paying for a budgeting app or handing their data to a third party.

> **Bank compatibility note:** The parser has been tested with a selection of US bank and credit card statement formats. Most standard PDF statements work well, but not every bank or format has been verified. If your statement doesn't parse correctly, see [Troubleshooting](#troubleshooting) or open a GitHub issue.

**Works with many banks** — Chase, Bank of America, Wells Fargo, Discover, credit unions, and more.

---

## Privacy

**Your financial data never leaves your computer.**

- No accounts to create
- No cloud uploads
- No subscriptions or fees
- All AI runs locally on your machine via [Ollama](https://ollama.com)

To verify: disconnect from the internet and the app still works completely.

---

## What You Need

- **Docker Desktop** — the only thing you need to install
- **Ollama** — a free local AI tool (runs AI models on your computer)
- An AI model downloaded through Ollama (instructions below)
- Your bank statement PDFs

That's it. Docker handles everything else.

---

## Installation

### Step 1 — Install Docker Desktop

Docker is what runs the application. Install it for your operating system:

<details>
<summary><strong>Windows</strong></summary>

1. Go to [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Click **Download for Windows**
3. Run the installer (`Docker Desktop Installer.exe`)
4. When asked, keep the default options and click **OK**
5. Restart your computer when prompted
6. After restart, open **Docker Desktop** from the Start menu and wait for it to say **"Engine running"** in the bottom left corner

> **Note:** Windows requires WSL 2 (Windows Subsystem for Linux). The Docker installer will set this up automatically on Windows 10/11.

</details>

<details>
<summary><strong>macOS</strong></summary>

1. Go to [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Choose **Download for Mac** — select **Apple Chip** if you have an M1/M2/M3 Mac, or **Intel Chip** for older Macs
   - Not sure which? Click the Apple menu → **About This Mac** — look for "Apple M" (Apple chip) or "Intel" in the chip description
3. Open the downloaded `.dmg` file and drag Docker to Applications
4. Open Docker from Applications and follow the prompts
5. Wait for the Docker menu bar icon to stop animating — it's ready when it shows **"Docker Desktop is running"**

</details>

<details>
<summary><strong>Linux (Ubuntu/Debian)</strong></summary>

Open a terminal and run:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt-get install docker-compose-plugin

# Log out and back in (so the group change takes effect), then start Docker
sudo systemctl enable docker
sudo systemctl start docker
```

> **Note:** After running `sudo usermod -aG docker $USER`, you must log out and log back in before running Docker commands without `sudo`.

</details>

---

### Step 2 — Install Ollama

Ollama runs the AI models that clean up merchant names and categorize transactions.

<details>
<summary><strong>Windows</strong></summary>

1. Go to [https://ollama.com/download/windows](https://ollama.com/download/windows)
2. Download and run the installer
3. Ollama will start automatically in the system tray

</details>

<details>
<summary><strong>macOS</strong></summary>

1. Go to [https://ollama.com/download](https://ollama.com/download)
2. Download the macOS app and move it to Applications
3. Open Ollama — it runs in the menu bar

</details>

<details>
<summary><strong>Linux</strong></summary>

Open a terminal and run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

</details>

---

### Step 3 — Download an AI Model

With Ollama installed, open a **Terminal** (macOS/Linux) or **Command Prompt / PowerShell** (Windows) and run:

```
ollama pull qwen2.5:14b
```

This downloads the AI model used to understand transaction descriptions. It's about 9 GB, so it may take a few minutes depending on your connection. You only need to do this once.

> **Lower-spec computers:** If your computer has less than 16 GB of RAM, use this lighter model instead:
> ```
> ollama pull qwen2.5:7b
> ```
> Then open `config/llm_models.json` in the project folder and change `"primary_model"` to `"qwen2.5:7b"`.

---

### Step 4 — Download and Start the App

<details>
<summary><strong>Windows</strong></summary>

1. Download the project:
   - If you have Git: open **Command Prompt** and run `git clone https://github.com/your-repo/AutomatedBudgeting.git`
   - Otherwise: download the ZIP from GitHub and extract it
2. Open **Command Prompt** and navigate to the folder:
   ```
   cd C:\Users\YourName\Documents\AutomatedBudgeting
   ```
3. Build and start the app:
   ```
   docker compose up --build -d
   ```
4. Wait about 2–3 minutes for the build to finish (one-time only)

</details>

<details>
<summary><strong>macOS</strong></summary>

1. Open **Terminal** (find it in Applications → Utilities)
2. Navigate to the project folder:
   ```bash
   cd ~/Documents/AutomatedBudgeting
   ```
3. Build and start the app:
   ```bash
   docker compose up --build -d
   ```
4. Wait about 2–3 minutes for the build to finish (one-time only)

</details>

<details>
<summary><strong>Linux</strong></summary>

1. Open a terminal and navigate to the project folder:
   ```bash
   cd ~/Documents/AutomatedBudgeting
   ```
2. Build and start the app:
   ```bash
   docker compose up --build -d
   ```
3. Wait about 2–3 minutes for the build to finish (one-time only)

</details>

---

### Step 5 — Open the Dashboard

Once the build is done, open your web browser and go to:

**[http://localhost:8000](http://localhost:8000)**

You should see the Automated Budgeting dashboard. 🎉

---

## Daily Use

### Starting the App

After the initial setup, starting the app is quick:

**Windows (Command Prompt):**
```
cd C:\Users\YourName\Documents\AutomatedBudgeting
docker compose up -d
```

**macOS / Linux (Terminal):**
```bash
cd ~/Documents/AutomatedBudgeting
docker compose up -d
```

Then open [http://localhost:8000](http://localhost:8000).

> **Shortcut:** You can bookmark `http://localhost:8000` in your browser. Just remember to start Docker Desktop and run `docker compose up -d` first each time.

---

### Stopping the App

**Windows (Command Prompt):**
```
docker compose down
```

**macOS / Linux (Terminal):**
```bash
docker compose down
```

Or just close Docker Desktop — the app will stop automatically.

---

## Using the Dashboard

### Uploading Your Bank Statements

1. In the dashboard, click the **Statements** tab
2. Select the month you want to process (e.g., `2025-03`)
3. Click **Upload PDF** and select your bank statement PDF
4. Repeat for any additional statements for that month (e.g., multiple bank accounts or credit cards)
5. Click **Process Statements** to extract all transactions

Processing takes about 30–60 seconds per statement depending on your computer's speed.

---

### Viewing Your Spending

The **Overview** tab shows:
- A **pie chart** of your spending by category for the selected month
- A **transactions table** below the chart — click any category slice to filter to just that category
- **Summary cards** showing total spend, income, and average monthly figures

Use the **month selector** in the top bar to switch between months.

---

### Transactions Tab

The **Transactions** tab shows every transaction across all months. From here you can:

- **Search** by merchant name
- **Filter** by type (expense, income, manual review)
- **Edit a merchant name** — click on any name in the Merchant column to rename it
- **Change a category** — click the category to open a dropdown and pick a new one
- **Change the label** — mark a transaction as Normal, One-Time, or Bonus
- **Add a transaction manually** — for cash purchases not on your statement

---

### Manual Review

Some transactions need your input — mainly payment app transfers (Venmo, Zelle, Cash App, PayPal) because they could be anything: rent, a gift, splitting a bill. The app flags these in the **Transactions** tab under the "Needs Review" section.

For each flagged item:
1. Choose **Expense** or **Income** from the dropdown
2. Pick a **category**
3. The transaction moves to your expenses or income automatically

---

### Adding Cash Transactions

Did you pay cash for something? You can add it manually:

1. Click the **Transactions** tab
2. Click **+ Add Transaction**
3. Fill in the date, merchant name, amount, and category
4. Click **Save**

It will appear immediately in your reports.

---

### Budget & Forecast Tab

The **Budget** tab shows:
- Month-over-month spending trends as a line chart
- Income vs. expenses comparison
- Category-level spending history

---

### Investments Tab

Any transaction you categorize as **Investment** or **Investment Transfer** appears in the **Investments** tab, separated from regular expenses.

---

## Categories

Transactions are automatically sorted into these categories:

| Category | Examples |
|---|---|
| Groceries | Supermarkets, food stores |
| Dining | Restaurants, fast food, coffee shops |
| Transportation | Gas, parking, rideshare, public transit |
| Utilities | Electric, gas, water, internet, phone |
| Healthcare | Doctor, pharmacy, dentist, vision |
| Shopping | Clothing, electronics, online retail |
| Entertainment | Streaming, movies, events, games |
| Personal Care | Salon, gym, spa |
| Home | Rent, mortgage, repairs, hardware |
| Insurance | Health, auto, home, life |
| Subscriptions | Monthly services |
| Auto Maintenance | Car repairs, registration |
| Education | Tuition, books, courses |
| Gifts & Charity | Donations, presents |
| Pet Care | Vet, food, grooming |
| Travel | Flights, hotels, vacation |
| Investment | Stocks, crypto, retirement contributions |
| Banking Fees | Overdraft fees, service charges |
| Return/Reimbursement | Refunds, credits |

If a transaction ends up in the wrong category, click it in the Transactions tab to change it. The app learns from your corrections.

### Customising Categories

All categories are defined in `config/categories.json`. You can add, rename, or remove categories by editing that file.

**Add a top-level category:**
1. Open `config/categories.json`
2. Add the new name to the `"categories"` array:
   ```json
   "categories": [
     "Groceries",
     "Dining",
     "Your New Category"
   ]
   ```
3. Restart the app (`docker compose up -d`). The new category will appear in dropdowns and charts immediately.

**Add a subcategory (rolls up to a parent in charts):**
1. Add the subcategory to the `"categories"` array
2. Add it under its parent in the `"hierarchy"` dict:
   ```json
   "hierarchy": {
     "Transportation": ["Gas/Fuel", "Auto Maintenance", "Your Subcategory"]
   }
   ```
Subcategories appear individually in transaction lists but are grouped under their parent in pie charts and budget summaries.

**Remove a category:**
1. Remove it from the `"categories"` array (and from `"hierarchy"` if it's listed there)
2. Any existing transactions with that category will keep the old label — re-categorize them from the Transactions tab

> **Tip:** Category names are case-sensitive. `"Groceries"` and `"groceries"` are treated as different categories.

---

## Troubleshooting

<details>
<summary><strong>The dashboard won't open / "This site can't be reached"</strong></summary>

1. Make sure Docker Desktop is open and running (look for the whale icon in your taskbar/menu bar)
2. Open a terminal and run `docker compose up -d` from the project folder
3. Wait 10–15 seconds and try again
4. If still not working, run `docker ps` — you should see a container named `automated-budgeting` with status `Up`

</details>

<details>
<summary><strong>"Error connecting to Ollama" when processing statements</strong></summary>

Ollama must be running before you process statements.

- **Windows/macOS:** Look for the Ollama icon in your system tray or menu bar. If it's not there, open Ollama from your Applications folder.
- **Linux:** Run `ollama serve` in a terminal, or check `systemctl status ollama`.

</details>

<details>
<summary><strong>Processing is very slow</strong></summary>

The first time you process a statement it takes longer because the AI model is loading into memory. Subsequent statements in the same session are faster.

If it consistently takes more than 5 minutes per statement, consider using a lighter model:
1. Open `config/llm_models.json` in the project folder
2. Change `"primary_model"` to `"qwen2.5:7b"` (download with `ollama pull qwen2.5:7b` first)

</details>

<details>
<summary><strong>Transactions are missing or the amounts look wrong</strong></summary>

Some PDF statements use unusual formatting that the parser struggles with. Try:
1. Download a fresh copy of the statement directly from your bank's website
2. Make sure it's a real PDF (not a scanned image saved as PDF — though OCR does help with these)
3. Open a GitHub issue with a description of which bank and what the problem looks like

</details>

<details>
<summary><strong>I updated the project files but the app isn't showing changes</strong></summary>

You need to rebuild the Docker image after updating code:
```
docker compose up --build -d
```

</details>

<details>
<summary><strong>Docker compose command not found (older systems)</strong></summary>

Older versions of Docker use `docker-compose` (with a hyphen) instead of `docker compose`:
```bash
docker-compose up -d
docker-compose down
docker-compose up --build -d
```

</details>

---

## Updating the App

To get the latest version:

```bash
# Pull the latest code
git pull

# Rebuild and restart
docker compose up --build -d
```

---

## Your Data

All your data lives in the `src/ui/data/` folder inside the project directory:

```
src/ui/data/
  statements/
    2025-01/    ← PDFs and processed CSVs for January 2025
    2025-02/    ← February 2025
    ...
  monthly_reports/
    expenses_2025-01.csv
    income_2025-01.csv
    ...
```

**To back up your data:** copy the `src/ui/data/` folder to an external drive or cloud storage.

**To move to a new computer:** copy the entire project folder, install Docker and Ollama on the new machine, and run `docker compose up --build -d`.

---

## Further Reading

For deeper technical information, see the [docs/](docs/INDEX.md) folder:

- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** — setting up a development environment
- **[Architecture Overview](docs/ARCHITECTURE.md)** — how all the pieces fit together
- **[PDF Parsing](docs/PARSING.md)** — how bank statements are read
- **[Categorization](docs/CATEGORIZATION.md)** — how transactions are categorized
- **[LLM Merchant Cleaning](docs/LLM_MERCHANT_CLEANING.md)** — how merchant names are cleaned up
- **[Dashboard & API](docs/DASHBOARD.md)** — the web UI and backend API

---

## License

MIT License — free to use, modify, and share.

---

*Built with FastAPI, React, pdfplumber, spaCy, and Ollama.*
