MCP_TOOLS = [
    {
        "name": "retailpulse_list_models",
        "description": "Auto-detect active Groq and Gemini models available for RetailPulse.",
        "inputSchema": {"type": "object", "properties": {"force": {"type": "boolean"}}},
    },
    {
        "name": "retailpulse_search_docs",
        "description": "Search RetailPulse SOPs, limitations, and metrics with grounded citations.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "retailpulse_inspect_shelf",
        "description": "Run CNN quality-gated shelf defect/stock classification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "brightness": {"type": "number"},
                "edge_density": {"type": "number"},
                "color_variance": {"type": "number"},
            },
            "required": ["brightness", "edge_density", "color_variance"],
        },
    },
]
