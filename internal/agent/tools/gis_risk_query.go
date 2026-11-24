package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/Tencent/WeKnora/internal/logger"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/utils"
	"gorm.io/gorm"
)

var gisRiskQueryTool = BaseTool{
	name: ToolGISRiskQuery,
	description: `查询园区传感器告警数据并在地图上标注风险点。

## 何时使用
当用户询问园区安全风险、传感器报警、地图上的风险点/风险区域、某区域的告警情况等问题时使用。
例如：「今天园区内是否有安全风险」「A区有哪些报警」「把今天的告警标在地图上」。

## 返回
- output: 风险摘要文字（用于向用户解释）
- data.geojson: GeoJSON FeatureCollection，前端据此渲染地图标注

## 参数
- area: 可选，区域过滤（A区/B区/C区），留空查全部区域
- date: 可选，查询日期 YYYY-MM-DD，留空默认今天（Asia/Shanghai）`,
	schema: utils.GenerateSchema[GISRiskQueryInput](),
}

// GISRiskQueryInput 是 gis_risk_query 工具的入参。
type GISRiskQueryInput struct {
	Area string `json:"area" jsonschema:"园区区域过滤，如 A区/B区/C区，可选，留空查全部区域"`
	Date string `json:"date" jsonschema:"查询日期，格式 YYYY-MM-DD，可选，留空默认今天（Asia/Shanghai 时区）"`
}

// GISRiskQueryTool 查询 sensor_alarms 表，分析告警并输出 GeoJSON。
type GISRiskQueryTool struct {
	BaseTool
	db *gorm.DB
}

// NewGISRiskQueryTool 创建 GIS 风险查询工具。
func NewGISRiskQueryTool(db *gorm.DB) *GISRiskQueryTool {
	return &GISRiskQueryTool{BaseTool: gisRiskQueryTool, db: db}
}

// sensorAlarmRow 是 sensor_alarms 表的一行。
type sensorAlarmRow struct {
	DeviceID     string    `gorm:"column:device_id"`
	SensorType   string    `gorm:"column:sensor_type"`
	TS           time.Time `gorm:"column:ts"`
	Value        string    `gorm:"column:value"`
	ValueNum     *float64  `gorm:"column:value_num"`
	Unit         string    `gorm:"column:unit"`
	Threshold    string    `gorm:"column:threshold"`
	ThresholdNum *float64  `gorm:"column:threshold_num"`
	AlarmLevel   string    `gorm:"column:alarm_level"`
	Lon          float64   `gorm:"column:lon"`
	Lat          float64   `gorm:"column:lat"`
	Area         string    `gorm:"column:area"`
	Building     string    `gorm:"column:building"`
}

// Execute 执行查询。
func (t *GISRiskQueryTool) Execute(ctx context.Context, args json.RawMessage) (*types.ToolResult, error) {
	logger.Infof(ctx, "[Tool][GISRiskQuery] Execute started")

	var input GISRiskQueryInput
	if err := json.Unmarshal(args, &input); err != nil {
		return &types.ToolResult{Success: false, Error: fmt.Sprintf("参数解析失败: %v", err)}, err
	}

	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		loc = time.FixedZone("CST", 8*3600)
	}

	var dayStart, dayEnd time.Time
	if input.Date != "" {
		d, perr := time.ParseInLocation("2006-01-02", input.Date, loc)
		if perr != nil {
			return &types.ToolResult{Success: false, Error: fmt.Sprintf("日期格式错误（应为 YYYY-MM-DD）: %v", perr)}, perr
		}
		dayStart = d
		dayEnd = d.AddDate(0, 0, 1)
	} else {
		now := time.Now().In(loc)
		y, m, dd := now.Date()
		dayStart = time.Date(y, m, dd, 0, 0, 0, 0, loc)
		dayEnd = dayStart.AddDate(0, 0, 1)
	}

	query := t.db.WithContext(ctx).Table("sensor_alarms").
		Where("alarm = ?", true).
		Where("ts >= ? AND ts < ?", dayStart, dayEnd)
	if input.Area != "" {
		query = query.Where("area = ?", input.Area)
	}

	var rows []sensorAlarmRow
	if err := query.Order("alarm_level DESC, ts ASC").Find(&rows).Error; err != nil {
		logger.Errorf(ctx, "[Tool][GISRiskQuery] query failed: %v", err)
		return &types.ToolResult{Success: false, Error: fmt.Sprintf("查询传感器数据失败: %v", err)}, err
	}

	summary := buildGISSummary(rows, input.Date, input.Area)
	geojson := buildGISGeoJSON(rows)
	center := []float64{116.276728, 40.051106} // 中国卫通后厂村路园区中心
	if len(rows) > 0 {
		center = []float64{rows[0].Lon, rows[0].Lat}
	}

	logger.Infof(ctx, "[Tool][GISRiskQuery] done: %d alarms", len(rows))
	return &types.ToolResult{
		Success: true,
		Output:  summary,
		Data: map[string]interface{}{
			"display_type": "gis_map",
			"geojson":      geojson,
			"summary":      summary,
			"center":       center,
			"alarm_count":  len(rows),
		},
	}, nil
}

// buildGISGeoJSON 把告警行转成 GeoJSON FeatureCollection。
func buildGISGeoJSON(rows []sensorAlarmRow) map[string]interface{} {
	features := make([]map[string]interface{}, 0, len(rows))
	for _, r := range rows {
		features = append(features, map[string]interface{}{
			"type": "Feature",
			"geometry": map[string]interface{}{
				"type":        "Point",
				"coordinates": []float64{r.Lon, r.Lat},
			},
			"properties": map[string]interface{}{
				"device_id":   r.DeviceID,
				"sensor_type": r.SensorType,
				"building":    r.Building,
				"area":        r.Area,
				"value":       r.Value,
				"unit":        r.Unit,
				"threshold":   r.Threshold,
				"alarm_level": r.AlarmLevel,
				"time":        r.TS.In(time.FixedZone("CST", 8*3600)).Format("15:04"),
				"description": alarmDescription(r),
			},
		})
	}
	return map[string]interface{}{
		"type":     "FeatureCollection",
		"features": features,
	}
}

// buildGISSummary 生成风险摘要文字。
func buildGISSummary(rows []sensorAlarmRow, date, area string) string {
	scope := "今天"
	if date != "" {
		scope = date
	}
	if area != "" {
		scope += " " + area
	}
	if len(rows) == 0 {
		return fmt.Sprintf("%s 未发现传感器报警，园区安全。", scope)
	}
	counts := map[string]int{}
	for _, r := range rows {
		counts[r.AlarmLevel]++
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%s 园区共发现 %d 个传感器报警", scope, len(rows))
	if n := counts["high"]; n > 0 {
		fmt.Fprintf(&b, "，其中高风险 %d 个", n)
	}
	if n := counts["medium"]; n > 0 {
		fmt.Fprintf(&b, "，中风险 %d 个", n)
	}
	if n := counts["low"]; n > 0 {
		fmt.Fprintf(&b, "，低风险 %d 个", n)
	}
	b.WriteString("。\n风险点：\n")
	for _, r := range rows {
		fmt.Fprintf(&b, "- %s\n", alarmDescription(r))
	}
	return strings.TrimRight(b.String(), "\n")
}

// alarmDescription 生成单条告警的中文描述。
func alarmDescription(r sensorAlarmRow) string {
	lv := map[string]string{"high": "高风险", "medium": "中风险", "low": "低风险"}[r.AlarmLevel]
	if lv == "" {
		lv = r.AlarmLevel
	}
	val := r.Value
	if r.Unit != "" {
		val = r.Value + r.Unit
	}
	return fmt.Sprintf("%s(%s) %s %s，当前值 %s（阈值 %s）", r.Building, r.Area, r.SensorType, lv, val, r.Threshold)
}
