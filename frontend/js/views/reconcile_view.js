export const reconcileViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>许可对账</h3>
      <div class="actions"><button class="secondary" @click="loadReconcile">刷新全部</button></div>
      <table>
        <thead><tr><th>许可</th><th>对齐</th><th>证明</th><th>封批数</th><th>累计流量 m3/h</th><th>口限剔除</th></tr></thead>
        <tbody>
          <tr v-for="r in reconAllItems" :key="r.permit_code">
            <td>{{ r.permit_code }}</td>
            <td :class="r.balanced?'pass':'fail'">{{ r.balanced ? "齐" : "不齐" }}</td>
            <td :class="r.proof_ready?'pass':'warn'">{{ r.proof_ready ? "可证" : "未齐" }}</td>
            <td>{{ r.seal_count || 0 }}</td>
            <td>{{ r.total_flow_m3h ?? 0 }}</td>
            <td :class="r.excluded_count ? 'fail' : 'muted'">{{ r.excluded_count || 0 }} 笔口限禁入剔除</td>
          </tr>
        </tbody>
      </table>
      <p class="muted" style="font-size:0.8rem;margin-top:0.5rem">
        累计流量仅含通过本口限值裁决的合规批；超口限批按“口限禁入”剔除，不累计其流量。
      </p>
    </div>
    <div class="panel">
      <h3>单许可 / 采样证明</h3>
      <label>许可号</label><input v-model="reconCode"/>
      <div class="actions"><button @click="loadReconcileOne">对账</button></div>
      <pre v-if="reconOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(reconOne, null, 2) }}</pre>
      <div v-if="reconOne && reconOne.excluded_samples && reconOne.excluded_samples.length" class="banner err" style="margin-top:0.5rem">
        口限禁入剔除：
        <span v-for="x in reconOne.excluded_samples" :key="x.sample_code">
          {{ x.sample_code }}（{{ x.outfall_code }} {{ x.exceed_metric }} {{ x.measured }}&gt;{{ x.limit_value }}，{{ x.flow_m3h }} m3/h 不计）；
        </span>
      </div>
      <label>采样号证明</label><input v-model="proofCode"/>
      <div class="actions"><button class="secondary" @click="loadProof">证明</button></div>
      <pre v-if="proofOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(proofOne, null, 2) }}</pre>
    </div>
  </div>`;
