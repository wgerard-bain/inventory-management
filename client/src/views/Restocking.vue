<template>
  <div class="restocking">
    <div class="page-header">
      <h2>Restocking</h2>
      <p>Budget-driven restock recommendations based on demand forecasts</p>
    </div>

    <div v-if="loading" class="loading">Loading demand forecasts...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Restock Budget</h3>
        </div>
        <div class="budget-control">
          <label for="budget-slider">Available Budget</label>
          <input
            id="budget-slider"
            type="range"
            min="0"
            :max="maxBudget || 0"
            step="50"
            v-model.number="budget"
            :disabled="maxBudget === 0"
            class="budget-slider"
          />
          <div class="budget-readout">${{ budget.toLocaleString() }}</div>
        </div>
        <p v-if="maxBudget === 0" class="empty-note">
          No recommendations available for the current filters.
        </p>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Budget</div>
          <div class="stat-value">${{ budget.toLocaleString() }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">Items Recommended</div>
          <div class="stat-value">{{ orderItems.length }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">Est. Order Total</div>
          <div class="stat-value">${{ orderTotal.toLocaleString() }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">Est. Delivery</div>
          <div class="stat-value">{{ estimatedDelivery ? `${estimatedDelivery} days` : '—' }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Recommended Restock Items</h3>
        </div>
        <div v-if="evaluatedItems.length === 0" style="padding: 3rem; text-align: center; color: #64748b;">
          No demand forecasts match the current filters.
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Item Name</th>
                <th>Trend</th>
                <th>Recommended Qty</th>
                <th>Unit Cost</th>
                <th>Line Cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in evaluatedItems" :key="item.id">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td><span class="badge" :class="item.trend">{{ item.trend }}</span></td>
                <td>{{ item.recommended_qty }}</td>
                <td>${{ item.unit_cost.toLocaleString() }}</td>
                <td>${{ item.line_cost.toLocaleString() }}</td>
                <td>
                  <span v-if="item.included" class="badge success">Included</span>
                  <span v-else class="badge warning">Skipped</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-actions">
          <button
            class="btn-primary"
            :disabled="orderItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? 'Placing Order...' : 'Place Order' }}
          </button>

          <div v-if="submitSuccess" class="success-banner">
            Order {{ submitSuccess }} placed successfully — check the Orders tab for delivery details.
          </div>
          <div v-if="submitError" class="error">{{ submitError }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useFilters } from '../composables/useFilters'
import { api } from '../api'

const { selectedLocation, selectedCategory } = useFilters()

const loading = ref(true)
const error = ref(null)
const allDemandForecasts = ref([])
const budget = ref(5000)
const submitting = ref(false)
const submitSuccess = ref(null)
const submitError = ref(null)

const TREND_ORDER = { increasing: 0, stable: 1, decreasing: 2 }

const loadDemandForecasts = async () => {
  try {
    loading.value = true
    error.value = null
    allDemandForecasts.value = await api.getDemandForecasts({
      warehouse: selectedLocation.value,
      category: selectedCategory.value
    })
  } catch (err) {
    error.value = 'Failed to load demand forecasts: ' + err.message
  } finally {
    loading.value = false
  }
}

const rankedRecommendations = computed(() => {
  const items = allDemandForecasts.value.map(item => {
    const growth_pct = item.current_demand > 0
      ? (item.forecasted_demand - item.current_demand) / item.current_demand * 100
      : 0
    const recommended_qty = Math.max(
      item.forecasted_demand - item.current_demand,
      Math.round(item.forecasted_demand * 0.10)
    )
    const line_cost = recommended_qty * item.unit_cost

    return { ...item, growth_pct, recommended_qty, line_cost }
  })

  return items.sort((a, b) => {
    const trendDiff = (TREND_ORDER[a.trend] ?? 1) - (TREND_ORDER[b.trend] ?? 1)
    if (trendDiff !== 0) return trendDiff
    return b.growth_pct - a.growth_pct
  })
})

const maxBudget = computed(() => {
  return rankedRecommendations.value.reduce((sum, item) => sum + item.line_cost, 0)
})

const evaluatedItems = computed(() => {
  let remaining = budget.value
  return rankedRecommendations.value.map(item => {
    if (item.line_cost <= remaining) {
      remaining -= item.line_cost
      return { ...item, included: true }
    }
    return { ...item, included: false }
  })
})

const orderItems = computed(() => evaluatedItems.value.filter(i => i.included))

const orderTotal = computed(() => orderItems.value.reduce((sum, i) => sum + i.line_cost, 0))

const estimatedDelivery = computed(() => {
  if (orderItems.value.length === 0) return 0
  return Math.max(...orderItems.value.map(i => i.lead_time_days))
})

const placeOrder = async () => {
  if (orderItems.value.length === 0) return

  submitting.value = true
  submitSuccess.value = null
  submitError.value = null

  try {
    const payload = {
      items: orderItems.value.map(i => ({
        item_sku: i.item_sku,
        item_name: i.item_name,
        quantity: i.recommended_qty,
        unit_cost: i.unit_cost,
        lead_time_days: i.lead_time_days
      })),
      budget: budget.value,
      warehouse: selectedLocation.value !== 'all' ? selectedLocation.value : null,
      category: selectedCategory.value !== 'all' ? selectedCategory.value : null
    }

    const result = await api.createRestockOrder(payload)
    submitSuccess.value = result.order_number
  } catch (err) {
    submitError.value = 'Failed to place order: ' + err.message
  } finally {
    submitting.value = false
  }
}

watch([selectedLocation, selectedCategory], loadDemandForecasts)
onMounted(loadDemandForecasts)
</script>

<style scoped>
.budget-control {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 1.25rem;
}

.budget-control label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}

.budget-readout {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 100px;
  text-align: right;
}

.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-webkit-slider-thumb:hover {
  background: #2563eb;
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-moz-range-thumb:hover {
  background: #2563eb;
}

.budget-slider::-moz-range-progress {
  background: #3b82f6;
  height: 6px;
  border-radius: 3px;
}

.empty-note {
  margin-top: 0.75rem;
  color: #64748b;
  font-size: 0.875rem;
}

.order-actions {
  margin-top: 1.25rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
}
</style>
