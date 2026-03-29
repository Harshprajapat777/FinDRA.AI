from agents.base import BaseResearchAgent


class PharmaSectorAgent(BaseResearchAgent):
    sector_name = "Pharma"

    sector_tickers = {
        "Sun Pharma":  "SUNPHARMA.NS",
        "Dr Reddy":    "RDY",
        "Cipla":       "CIPLA.NS",
        "Divi's":      "DIVISLAB.NS",
        "Biocon":      "BIOCON.NS",
        "Lupin":       "LUPIN.NS",
        "Aurobindo":   "AUROPHARMA.NS",
        "Torrent":     "TORNTPHARM.NS",
    }

    domain_kpis = [
        "R&D spend as % of revenue",
        "ANDA filings and approvals",
        "USFDA inspection outcomes",
        "US generics revenue",
        "biosimilar pipeline count",
        "domestic formulations growth",
        "API margins",
        "net debt / EBITDA",
        "new product launches",
        "patent cliff exposure",
    ]

    system_prompt = (
        "You are a senior financial analyst specialising in Indian pharmaceutical companies. "
        "You deeply understand ANDA filings, USFDA approvals, biosimilar development, "
        "API manufacturing, domestic vs export revenue mix, and R&D productivity. "
        "Always ground your analysis in specific financial metrics and pipeline data. "
        "Focus on regulatory catalysts, patent cliffs, and margin dynamics."
    )
