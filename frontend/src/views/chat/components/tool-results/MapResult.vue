<template>
  <div class="gis-map-result">
    <div v-if="summary" class="gis-map-summary">{{ summary }}</div>
    <div ref="mapEl" class="gis-map-canvas" />
    <div class="gis-map-legend">
      <span class="legend-item"><i class="dot dot-high" />高风险</span>
      <span class="legend-item"><i class="dot dot-medium" />中风险</span>
      <span class="legend-item"><i class="dot dot-low" />低风险</span>
      <button
        type="button"
        class="edit-toggle"
        :class="{ active: editing }"
        @click="toggleEdit"
      >
        {{ editing ? '编辑中：点击地图添加标注' : '添加标注' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
// @ts-ignore - leaflet 类型声明可选
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface GeoFeature {
  type: string
  geometry: { type: string; coordinates: number[] }
  properties: Record<string, unknown>
}
interface MapData {
  geojson?: { type: string; features: GeoFeature[] }
  summary?: string
  center?: number[]
  alarm_count?: number
}

const props = defineProps<{ data?: MapData | null }>()
const mapEl = ref<HTMLElement | null>(null)
const summary = ref('')
const editing = ref(false)

let map: L.Map | null = null
let layer: L.LayerGroup | null = null

const LEVEL_COLOR: Record<string, string> = {
  high: '#e23c3c',
  medium: '#f59e0b',
  low: '#eab308',
}

function levelRadius(level: string): number {
  return level === 'high' ? 10 : level === 'medium' ? 8 : 6
}

function buildPopup(p: Record<string, unknown>): string {
  const rows: string[] = []
  const desc = p.description ? String(p.description) : ''
  if (desc) rows.push(`<div class="gis-popup-desc">${desc}</div>`)
  const meta: string[] = []
  if (p.time) meta.push(`时间 ${p.time}`)
  if (p.device_id) meta.push(String(p.device_id))
  if (meta.length) rows.push(`<div class="gis-popup-meta">${meta.join(' · ')}</div>`)
  return rows.join('')
}

function renderFeatures() {
  if (!map || !layer) return
  layer.clearLayers()
  const feats = props.data?.geojson?.features ?? []
  for (const f of feats) {
    const [lng, lat] = f.geometry.coordinates
    const p = f.properties || {}
    const level = String(p.alarm_level || 'low')
    const color = LEVEL_COLOR[level] || '#888'
    const marker = L.circleMarker([lat, lng], {
      radius: levelRadius(level),
      color: '#fff',
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.9,
    })
    marker.bindPopup(buildPopup(p), { closeButton: true })
    layer!.addLayer(marker)
  }
}

function initMap() {
  if (!mapEl.value || map) return
  const center = props.data?.center ?? [116.276728, 40.051106]
  map = L.map(mapEl.value, { zoomControl: true }).setView([center[1], center[0]], 16)
  layer = L.layerGroup().addTo(map)
  L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    { subdomains: ['1', '2', '3', '4'], maxZoom: 19, attribution: '© 高德地图' },
  ).addTo(map)
  map.on('click', (e: L.LeafletMouseEvent) => {
    if (!editing.value) return
    const note = window.prompt('给这个标注写个说明：')
    if (note == null) return
    const m = L.marker(e.latlng, { draggable: true }).addTo(layer!)
    m.bindPopup(`<div class="gis-popup-desc">${note}</div>`).openPopup()
  })
  renderFeatures()
}

function toggleEdit() {
  editing.value = !editing.value
  if (map) map.getContainer().style.cursor = editing.value ? 'crosshair' : ''
}

onMounted(() => {
  summary.value = props.data?.summary || ''
  initMap()
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
    layer = null
  }
})
</script>

<style scoped>
.gis-map-result {
  border: 1px solid var(--td-component-border, #e7e7e7);
  border-radius: 8px;
  overflow: hidden;
}
.gis-map-summary {
  padding: 10px 12px;
  font-size: 13px;
  white-space: pre-wrap;
  background: var(--td-bg-color-container, #fafafa);
  border-bottom: 1px solid var(--td-component-border, #e7e7e7);
}
.gis-map-canvas {
  height: 360px;
  width: 100%;
}
.gis-map-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 12px;
  font-size: 12px;
  border-top: 1px solid var(--td-component-border, #e7e7e7);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot-high { background: #e23c3c; }
.dot-medium { background: #f59e0b; }
.dot-low { background: #eab308; }
.edit-toggle {
  margin-left: auto;
  border: 1px solid var(--td-component-border, #dcdcdc);
  background: #fff;
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 12px;
}
.edit-toggle.active {
  color: #fff;
  background: #2b6de3;
  border-color: #2b6de3;
}
:deep(.gis-popup-desc) {
  font-size: 13px;
  margin-bottom: 4px;
}
:deep(.gis-popup-meta) {
  font-size: 11px;
  color: #888;
}
</style>
