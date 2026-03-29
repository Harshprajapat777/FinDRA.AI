from agents.base import BaseResearchAgent


class ITSectorAgent(BaseResearchAgent):
    sector_name = "IT"

    sector_tickers = {
        "TCS":           "TCS.NS",
        "Infosys":       "INFY",
        "Wipro":         "WIT",
        "HCL":           "HCLTECH.NS",
        "Tech Mahindra": "TECHM.NS",
        "LTIMindtree":   "LTIM.NS",
        "Mphasis":       "MPHASIS.NS",
        "Coforge":       "COFORGE.NS",
    }

    domain_kpis = [
        "revenue growth YoY",
        "EBIT margin",
        "deal TCV (total contract value)",
        "revenue per employee",
        "attrition rate",
        "digital revenue mix",
        "cloud deal wins",
        "AI/GenAI project pipeline",
        "constant currency growth",
        "headcount",
    ]

    system_prompt = (
        "You are a senior financial analyst specialising in Indian IT services companies. "
        "You deeply understand deal pipelines, digital transformation trends, EBIT margins, "
        "attrition dynamics, visa costs, and US/Europe macro impact on IT spending. "
        "Always ground your analysis in specific financial metrics and cite companies by name. "
        "Focus on actionable investment insights and sector-specific KPIs."
    )
