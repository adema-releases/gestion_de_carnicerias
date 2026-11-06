// Minimal app.js to power demo templates
const vendors = [
  {id:1,name:'Artesanías Luna',category:'artesanias',desc:'Piezas hechas a mano',image:''},
  {id:2,name:'Delicias Caseras',category:'gastronomia',desc:'Sabores caseros',image:''},
  {id:3,name:'Moda Sostenible',category:'moda',desc:'Ropa eco',image:''},
  {id:4,name:'Belleza Natural',category:'belleza',desc:'Productos orgánicos',image:''}
]

function $(sel){return document.querySelector(sel)}

function createVendorCard(v){
  const div=document.createElement('div');div.className='vendor-card'
  div.innerHTML = `
    <div class="vendor-image" style="background-image:url('/static/img/placeholder.png')"></div>
    <div class="vendor-header">
      <div class="vendor-avatar" style="background-image:url('/static/img/placeholder.png')"></div>
      <div class="vendor-info"><h3>${v.name}</h3><div class="vendor-category">${v.category}</div></div>
    </div>
    <div class="vendor-description">${v.desc}</div>
    <div class="vendor-actions"><a class="btn btn-secondary" href="#">Ver</a></div>
  `
  return div
}

function loadVendorsToGrid(){
  const grid = $('#feedGrid')
  if(!grid) return
  grid.innerHTML=''
  vendors.forEach(v=>grid.appendChild(createVendorCard(v)))
}

function performSearch(){
  const q = (document.getElementById('searchInput')||{}).value || ''
  const cat = (document.getElementById('categoryFilter')||{}).value || ''
  const filtered = vendors.filter(v=>v.name.toLowerCase().includes(q.toLowerCase()) && (cat? v.category===cat : true))
  const grid = document.getElementById('feedGrid')
  if(grid){grid.innerHTML=''; filtered.forEach(v=>grid.appendChild(createVendorCard(v)))}
}

function scrollToFeed(){document.getElementById('feedGrid')?.scrollIntoView({behavior:'smooth'})}

// Simple auth mock using localStorage
function loginUser(){
  const email = document.querySelector('#loginForm #email').value
  const password = document.querySelector('#loginForm #password').value
  if(!email||!password){showAuthError('Completa los campos', 'login');return}
  localStorage.setItem('feri_user', JSON.stringify({email}))
  window.location.href='/'
}

function registerUser(){
  const email = document.querySelector('#registerForm #email').value
  const password = document.querySelector('#registerForm #password').value
  const confirm = document.querySelector('#registerForm #confirmPassword').value
  if(password!==confirm){showAuthError('Las contraseñas no coinciden', 'register');return}
  localStorage.setItem('feri_user', JSON.stringify({email}))
  window.location.href='/'
}

function showAuthError(msg, form='login'){
  const el = document.querySelector((form==='login')? '#loginForm #authError' : '#registerForm #authError')
  if(el){el.textContent=msg}
}

function checkAuthState(){
  const u = localStorage.getItem('feri_user')
  if(u){document.querySelectorAll('.auth-section, #authSection').forEach(el=>el.innerHTML = `<span class="user-name">${JSON.parse(u).email}</span><a class="btn btn-outline" href="#" onclick="logout()">Salir</a>`)}
}

function logout(){localStorage.removeItem('feri_user');window.location.href='/'}

document.addEventListener('DOMContentLoaded', ()=>{loadVendorsToGrid();checkAuthState()})
