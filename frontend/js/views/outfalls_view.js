export const outfallsViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>排放口限值</h3>
      <table>
        <thead><tr><th>编码</th><th>厂</th><th>河段</th><th>COD 限</th><th>氨氮限</th><th>总磷限</th><th>状态</th><th>口限灯</th></tr></thead>
        <tbody>
          <tr v-for="o in outfalls" :key="o.id">
            <td>{{ o.outfall_code }}</td><td>{{ o.plant_code }}</td><td>{{ o.river_reach }}</td>
            <td>{{ o.cod_limit }}</td><td>{{ o.nh3n_limit }}</td><td>{{ o.tp_limit }}</td>
            <td :class="statusClass(o.status)">{{ o.status }}</td>
            <td>
              <span v-if="o.limit_alarm" class="fail">红灯 · {{ o.alarm_metric }} 超口限（最新 {{ o.latest_cod }}）</span>
              <span v-else class="pass">正常</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="muted" style="font-size:0.8rem;margin-top:0.5rem">
        口限灯由后端按本口限值统一裁决（与采样拒写、对账剔除同源）；红灯期间该口超口限批采样页拒建正式批。
      </p>
    </div>
    <div class="panel">
      <h3>新建排放口</h3>
      <div class="form-row"><div><label>编码</label><input v-model="outfallForm.outfall_code"/></div>
      <div><label>处理厂 ID</label><input type="number" v-model.number="outfallForm.plant_id"/></div></div>
      <label>河段</label><input v-model="outfallForm.river_reach"/>
      <div class="form-row">
        <div><label>COD 限</label><input type="number" v-model.number="outfallForm.cod_limit"/></div>
        <div><label>氨氮限</label><input type="number" v-model.number="outfallForm.nh3n_limit"/></div>
      </div>
      <label>总磷限</label><input type="number" v-model.number="outfallForm.tp_limit"/>
      <div class="actions"><button @click="createOutfall">登记</button></div>
    </div>
  </div>`;
