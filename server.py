from mcp.server.fastmcp import FastMCP
import datetime

mcp = FastMCP(
    name="Car Value",
    host="0.0.0.0",
    port=8050,  # only used for SSE transport (set this to any port)
)


@mcp.tool()
def get_car_value(model: str, year: int) -> int:
    """Retrieve the value of a car based on its model and year.

    Args:
        model: The model of the car.
        year: The manufacturing year of the car.

    Returns:
        An estimated value of the car.
    """
    # Placeholder logic for car value estimation
    base_value = 20000
    depreciation_rate = 0.15 if model.lower() == "sedan" else 0.20
    age = datetime.date.today().year - year
    estimated_value = int(base_value * ((1 - depreciation_rate) ** age))
    return estimated_value


if __name__ == "__main__":
    mcp.run(transport="stdio")
