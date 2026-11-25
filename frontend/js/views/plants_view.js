export const plantsViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>处理厂</h3>
      <table>
        <thead><tr><th>编码</th><th>名称</th><th>流域</th><th>设计量</th><th>状态</th><th>口数</th></tr></thead>
        <tbody>
          <tr v-for="p in plants" :key="p.id" @click="loadPlant(p.id)" style="cursor:pointer">
            <td>{{ p.plant_code }}</td><td>{{ p.name }}</td><td>{{ p.basin }}</td>
            <td>{{ p.design_cap_m3d }}</td><td :class="statusClass(p.status)">{{ p.status }}</td>
            <td>{{ p.outfall_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>新建处理厂</h3>
      <div class="form-row"><div><label>编码</label><input v-model="plantForm.plant_code"/></div>
      <div><label>名称</label><input v-model="plantForm.name"/></div></div>
      <div class="form-row"><div><label>流域</label><input v-model="plantForm.basin"/></div>
      <div><label>设计量 m3/d</label><input type="number" v-model.number="plantForm.design_cap_m3d"/></div></div>
      <div class="actions"><button @click="createPlant">登记</button></div>
      <div v-if="plantDetail" style="margin-top:1rem">
        <h3>详情 {{ plantDetail.plant.plant_code }}</h3>
        <div class="kv">
          <span>名称</span><span>{{ plantDetail.plant.name }}</span>
          <span>排放口</span><span>{{ plantDetail.outfalls.length }}</span>
          <span>许可</span><span>{{ plantDetail.permits.length }}</span>
        </div>
        <table style="margin-top:0.6rem">
          <thead><tr><th>排放口</th><th>COD 限</th><th>氨氮限</th><th>总磷限</th><th>口限告警条</th></tr></thead>
          <tbody>
            <tr v-for="o in plantDetail.outfalls" :key="o.id">
              <td>{{ o.outfall_code }}</td>
              <td>{{ o.cod_limit }}</td><td>{{ o.nh3n_limit }}</td><td>{{ o.tp_limit }}</td>
              <td>
                <span v-if="o.limit_alarm" class="fail">红灯 · {{ o.alarm_metric }} 超口限（最新 {{ o.latest_cod }}）</span>
                <span v-else class="pass">正常</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
