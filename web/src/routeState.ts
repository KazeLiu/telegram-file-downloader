import type { LocationQueryValue } from 'vue-router'

export function queryText(value: LocationQueryValue | LocationQueryValue[] | undefined) {
  return (Array.isArray(value) ? value[0] : value) || ''
}

export function queryPage(value: LocationQueryValue | LocationQueryValue[] | undefined) {
  const page = Number(queryText(value))
  return Number.isSafeInteger(page) && page > 0 ? page : 1
}
