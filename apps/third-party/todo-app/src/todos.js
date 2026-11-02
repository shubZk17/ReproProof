// Pinned Todo business logic for ReproProof R12 third-party testing

let todos = [
  { id: "todo-1", title: "Buy groceries", completed: false },
  { id: "todo-2", title: "File tax return", completed: true },
];

function getTodos() {
  return todos;
}

function addTodo(title) {
  const newTodo = {
    id: `todo-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    title,
    completed: false,
  };
  todos.push(newTodo);
  return newTodo;
}

function toggleTodo(id) {
  const todo = todos.find(t => t.id === id);
  if (todo) {
    todo.completed = !todo.completed;
  }
  return todo;
}

// SEEDED DEFECT: inverts completion filter so active items get deleted instead of completed items!
function clearCompleted() {
  // BUG: keeps completed items instead of uncompleted items
  todos = todos.filter(t => t.completed === true);
  return todos;
}

function resetTodos() {
  todos = [
    { id: "todo-1", title: "Buy groceries", completed: false },
    { id: "todo-2", title: "File tax return", completed: true },
  ];
  return todos;
}

module.exports = {
  getTodos,
  addTodo,
  toggleTodo,
  clearCompleted,
  resetTodos,
};
