import httpx

API_BASE_URL = "http://127.0.0.1:8000"


def get_merchants() -> list[dict]:
    response = httpx.get(
        f"{API_BASE_URL}/dashboard/merchants",
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def get_merchant_metrics(merchant_id: str) -> dict:
    response = httpx.get(
        f"{API_BASE_URL}/dashboard/metrics/{merchant_id}",
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def get_cases(
    merchant_id: str,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict:
    params = {
        "merchant_id": merchant_id,
        "limit": limit,
        "offset": offset,
    }
    if status:
        params["status"] = status

    response = httpx.get(
        f"{API_BASE_URL}/dashboard/cases",
        params=params,
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def get_case_detail(merchant_id: str, case_id: str) -> dict:
    response = httpx.get(
        f"{API_BASE_URL}/dashboard/cases/{case_id}",
        params={"merchant_id": merchant_id},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()