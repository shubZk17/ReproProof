// Seeded inventory business logic for ReproProof demo app

const initialItems = [
  { id: "item-1", name: "Widget A", count: 10 },
  { id: "item-2", name: "Widget B", count: 5 },
  { id: "item-3", name: "Widget C", count: 20 },
];

let itemsStore = JSON.parse(JSON.stringify(initialItems));

function getItems() {
  return itemsStore;
}

function addItem(name, count) {
  const newItem = {
    id: `item-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    name,
    count: parseInt(count, 10) || 1,
  };
  itemsStore.push(newItem);
  return newItem;
}

// SEEDED DEFECT: deletes the first item (index 0) instead of matching the specific id
function deleteItem(id) {
  const index = itemsStore.findIndex(item => item.id === id);
  if (index === -1) {
    return false;
  }
  // BUG: ignores index and always removes the first element (index 0)
  itemsStore.splice(0, 1);
  return true;
}

function resetItems() {
  itemsStore = JSON.parse(JSON.stringify(initialItems));
  return itemsStore;
}

module.exports = {
  getItems,
  addItem,
  deleteItem,
  resetItems,
};
