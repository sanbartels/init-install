-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not (vim.uv or vim.loop).fs_stat(lazypath) then
  local lazyrepo = "https://github.com/folke/lazy.nvim.git"
  local out = vim.fn.system({ "git", "clone", "--filter=blob:none", "--branch=stable", lazyrepo, lazypath })
  if vim.v.shell_error ~= 0 then
    vim.api.nvim_echo({
      { "Failed to clone lazy.nvim:\n", "ErrorMsg" },
      { out, "WarningMsg" },
      { "\nPress any key to exit..." },
    }, true, {})
    vim.fn.getchar()
    os.exit(1)
  end
end
vim.opt.rtp:prepend(lazypath)

-- Leader keys (debe ir antes de cargar lazy)
vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

-- Numeros de linea
vim.opt.number         = true   -- numero absoluto en la linea actual
vim.opt.relativenumber = true   -- numeros relativos en el resto (facilita saltar con Nj/Nk)
vim.opt.signcolumn     = "yes"  -- siempre visible para no saltar el layout
vim.opt.clipboard      = "unnamedplus" -- yank/delete usa el portapapeles del sistema





-- Registrar .graphqls como filetype graphql (extension de Spring GraphQL)
vim.filetype.add({
  extension = { graphqls = "graphql" },
})

-- Sin swapfiles (usamos auto-session para recuperar sesiones)
vim.opt.swapfile = false
vim.opt.backup   = false

-- Indentacion
vim.opt.tabstop     = 4     -- tab visual de 4 espacios
vim.opt.shiftwidth  = 4     -- indentacion con >> y auto-indent
vim.opt.softtabstop = 4     -- tab en modo insercion
vim.opt.expandtab   = true  -- convierte tabs a espacios
vim.opt.smartindent = true  -- auto-indent inteligente

-- Cerrar buffer actual
vim.keymap.set("n", "<leader>q", "<cmd>bdelete<cr>", { silent = true, desc = "Cerrar buffer" })

-- Guardar archivo
vim.keymap.set({ "n", "i", "v" }, "<C-s>", "<cmd>w<cr><esc>", { silent = true, desc = "Guardar archivo" })

-- Navegar entre buffers con Ctrl+h/l
vim.keymap.set("n", "<C-h>", "<cmd>BufferLineCyclePrev<cr>", { silent = true, desc = "Buffer anterior" })
vim.keymap.set("n", "<C-l>", "<cmd>BufferLineCycleNext<cr>", { silent = true, desc = "Siguiente buffer" })

-- Scroll: manejado por neoscroll con Ctrl+j/k

-- Navegar entre lineas vacias (enters): Alt+j/k
vim.keymap.set("n", "<M-j>", "}", { silent = true, desc = "Siguiente parrafo/bloque" })
vim.keymap.set("n", "<M-k>", "{", { silent = true, desc = "Parrafo/bloque anterior" })

-- Better escape: jk o jj para salir de insert mode
vim.keymap.set("i", "jk", "<Esc>", { silent = true, desc = "Salir insert mode" })
vim.keymap.set("i", "jj", "<Esc>", { silent = true, desc = "Salir insert mode" })

-- Setup lazy.nvim
require("lazy").setup({
  spec = {
    { import = "plugins" },
  },
  install = { colorscheme = { "tokyonight" } },
  checker = { enabled = true },
})
