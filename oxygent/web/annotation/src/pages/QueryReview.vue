<template>
  <div>
    <h2>Query Review (Minimal)</h2>
    <div>
      <input v-model="q" placeholder="search" />
      <button @click="search">Search</button>
    </div>
    <div v-if="items.length">
      <ul>
        <li v-for="it in items" :key="it.id">{{ it.user_query }} -> {{ it.agent_response }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { searchAnnotations } from '../api/annotation'

const q = ref('')
const items = ref([] as any[])

async function search() {
  const res = await searchAnnotations(q.value)
  items.value = res.data
}
</script>