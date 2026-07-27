"""
Tests for restocking order API endpoints.
"""
import sys
from pathlib import Path

import pytest

server_path = Path(__file__).parent.parent.parent / "server"
sys.path.insert(0, str(server_path))

import main


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """Restock orders live in a plain in-memory list, so reset it before each test
    to keep tests independent of execution order."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


class TestRestockOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_restock_orders_empty_initially(self, client):
        """Test that restock orders are empty before any are created."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order_success(self, client):
        """Test successfully creating a restock order."""
        payload = {
            "items": [
                {
                    "item_sku": "WDG-001",
                    "item_name": "Industrial Widget Type A",
                    "quantity": 150,
                    "unit_cost": 42.50,
                    "lead_time_days": 18
                }
            ],
            "budget": 7000,
            "warehouse": "San Francisco",
            "category": None
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["total_value"] == pytest.approx(150 * 42.50)
        assert order["budget"] == 7000
        assert order["warehouse"] == "San Francisco"
        assert "id" in order
        assert "order_number" in order
        assert "order_date" in order
        assert "expected_delivery" in order

    def test_create_restock_order_empty_items_rejected(self, client):
        """Test that an order with no items is rejected."""
        payload = {"items": [], "budget": 100}
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_created_order_appears_in_get(self, client):
        """Test that a newly created order shows up in the GET list."""
        payload = {
            "items": [
                {
                    "item_sku": "GSK-203",
                    "item_name": "High-Temperature Gasket",
                    "quantity": 100,
                    "unit_cost": 3.15,
                    "lead_time_days": 7
                }
            ],
            "budget": 500,
            "warehouse": "Tokyo",
            "category": "Actuators"
        }
        create_response = client.post("/api/restock-orders", json=payload)
        assert create_response.status_code == 200
        created_order_number = create_response.json()["order_number"]

        list_response = client.get("/api/restock-orders")
        assert list_response.status_code == 200

        data = list_response.json()
        assert len(data) == 1
        assert data[0]["order_number"] == created_order_number

    def test_restock_order_multiple_items_uses_max_lead_time(self, client):
        """Test that expected_delivery reflects the max lead time across items, not sum or average."""
        payload = {
            "items": [
                {
                    "item_sku": "FLT-405",
                    "item_name": "Oil Filter Cartridge",
                    "quantity": 150,
                    "unit_cost": 6.50,
                    "lead_time_days": 5
                },
                {
                    "item_sku": "MTR-304",
                    "item_name": "Electric Motor 5HP",
                    "quantity": 4,
                    "unit_cost": 285.00,
                    "lead_time_days": 35
                }
            ],
            "budget": 5000,
            "warehouse": None,
            "category": None
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 200

        order = response.json()

        from datetime import datetime
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        delta_days = (expected_delivery - order_date).days

        assert delta_days == 35

    def test_restock_order_total_value_calculation(self, client):
        """Test that total_value is the sum of quantity * unit_cost across items."""
        payload = {
            "items": [
                {
                    "item_sku": "SNR-420",
                    "item_name": "Temperature Sensor Module",
                    "quantity": 18,
                    "unit_cost": 15.75,
                    "lead_time_days": 9
                },
                {
                    "item_sku": "CTL-330",
                    "item_name": "Logic Controller Board",
                    "quantity": 10,
                    "unit_cost": 65.00,
                    "lead_time_days": 16
                }
            ],
            "budget": 1500,
            "warehouse": None,
            "category": None
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        expected_total = (18 * 15.75) + (10 * 65.00)
        assert order["total_value"] == pytest.approx(expected_total)
