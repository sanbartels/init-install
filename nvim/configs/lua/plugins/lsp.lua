-- ============================================================
-- Keymaps al conectar cualquier LSP
-- ============================================================
vim.api.nvim_create_autocmd("LspAttach", {
  group = vim.api.nvim_create_augroup("lsp_keymaps", { clear = true }),
  callback = function(event)
    local bufnr = event.buf
    local map = function(mode, lhs, rhs, desc)
      vim.keymap.set(mode, lhs, rhs, { buffer = bufnr, silent = true, desc = desc })
    end

    -- Navegacion
    map("n", "gd",  vim.lsp.buf.definition,      "Ir a definicion")
    map("n", "gD",  vim.lsp.buf.declaration,     "Ir a declaracion")
    map("n", "gi",  vim.lsp.buf.implementation,  "Implementacion")
    map("n", "gt",  vim.lsp.buf.type_definition, "Tipo de definicion")

    -- Referencias con Telescope
    map("n", "gr", function()
      require("telescope.builtin").lsp_references({ show_line = true, include_declaration = false })
    end, "Ver usos / referencias")
    map("n", "gR", function()
      require("telescope.builtin").lsp_references({ show_line = true, include_declaration = true })
    end, "Ver usos + declaracion")

    -- Ctrl+Click
    map("n", "<C-LeftMouse>", "<LeftMouse><cmd>lua vim.lsp.buf.definition()<cr>", "Ir a definicion (click)")

    -- Informacion
    map("n", "K",         vim.lsp.buf.hover,         "Documentacion")
    map("n", "<leader>k", vim.lsp.buf.signature_help, "Firma")

    -- Ctrl+Space en insert
    map("i", "<C-Space>", vim.lsp.buf.completion, "Sugerencias / importar")

    -- Alt+Enter: code actions (estilo IntelliJ)
    map("n", "<M-CR>", vim.lsp.buf.code_action, "Code actions")
    map("i", "<M-CR>", vim.lsp.buf.code_action, "Code actions")
    map("v", "<M-CR>", vim.lsp.buf.code_action, "Code actions")

    -- Leader
    map("n", "<leader>ca", vim.lsp.buf.code_action, "Code action")
    map("n", "<leader>rn", vim.lsp.buf.rename,      "Renombrar")
    map("n", "<leader>cf", function() vim.lsp.buf.format({ async = true }) end, "Formatear")
    map("n", "<leader>ju", function()
      require("telescope.builtin").lsp_references({ show_line = true, include_declaration = false })
    end, "Ver usos")

    -- Diagnosticos
    map("n", "[d",         vim.diagnostic.goto_prev,  "Diagnostico anterior")
    map("n", "]d",         vim.diagnostic.goto_next,  "Diagnostico siguiente")
    map("n", "<leader>dd", vim.diagnostic.open_float, "Ver diagnostico")
    map("n", "<leader>dl", vim.diagnostic.setloclist, "Lista diagnosticos")
  end,
})

-- ============================================================
-- Diagnostics visual
-- ============================================================
vim.diagnostic.config({
  virtual_text = { prefix = "●" },
  signs = true,
  underline = true,
  update_in_insert = false,
  severity_sort = true,
  float = { border = "rounded", source = true },
})

-- ============================================================
-- Plugins
-- ============================================================
return {
  -- nvim-lspconfig: provee los configs (cmd, filetypes, root_dir) para cada server
  -- mason-lspconfig los encuentra en lsp/ del runtimepath y llama vim.lsp.enable()
  {
    "neovim/nvim-lspconfig",
    dependencies = {
      { "mason-org/mason.nvim",            build = ":MasonUpdate", opts = {
          ui = {
            border = "rounded",
            icons = {
              package_installed   = "✓",
              package_pending     = "➜",
              package_uninstalled = "✗",
            },
          },
        },
      },
      { "mason-org/mason-lspconfig.nvim",  opts = {
          ensure_installed = {
            "vtsls",                   -- TypeScript / React / React Router 7
            "cssls",                   -- CSS
            "html",                    -- HTML
            "jsonls",                  -- JSON
            "lua_ls",                  -- Lua
            "emmet_language_server",   -- Emmet para JSX/HTML
            "jdtls",                   -- Java; lo activa nvim-jdtls via ftplugin
          },
          -- jdtls lo maneja nvim-jdtls via ftplugin
          automatic_enable = {
            exclude = { "jdtls" },
          },
        },
      },
      { "b0o/schemastore.nvim", lazy = true },
    },
    config = function()
      -- Extender settings de cada server DESPUES de que nvim-lspconfig
      -- haya puesto sus configs en el runtimepath

      -- vtsls: TypeScript / JavaScript / React / React Router 7
      vim.lsp.config("vtsls", {
        settings = {
          vtsls = {
            enableMoveToFileCodeAction = true,
            autoUseWorkspaceTsdk      = true,
          },
          typescript = {
            updateImportsOnFileMove = { enabled = "always" },
            preferences = {
              importModuleSpecifier            = "non-relative", -- preferir alias sobre rutas relativas
              importModuleSpecifierEnding      = "minimal",
              autoImportFileExcludePatterns    = {},
            },
            suggest                 = { completeFunctionCalls = true },
            inlayHints = {
              enumMemberValues         = { enabled = true },
              functionLikeReturnTypes  = { enabled = true },
              parameterNames           = { enabled = "literals" },
              parameterTypes           = { enabled = true },
              propertyDeclarationTypes = { enabled = true },
              variableTypes            = { enabled = false },
            },
          },
          javascript = {
            updateImportsOnFileMove = { enabled = "always" },
            suggest                 = { completeFunctionCalls = true },
            preferences = {
              importModuleSpecifier       = "non-relative",
              importModuleSpecifierEnding = "minimal",
            },
            inlayHints = {
              enumMemberValues         = { enabled = true },
              functionLikeReturnTypes  = { enabled = true },
              parameterNames           = { enabled = "literals" },
              parameterTypes           = { enabled = true },
              propertyDeclarationTypes = { enabled = true },
              variableTypes            = { enabled = false },
            },
          },
        },
      })

      -- lua_ls
      vim.lsp.config("lua_ls", {
        settings = {
          Lua = {
            runtime     = { version = "LuaJIT" },
            workspace   = {
              checkThirdParty = false,
              library         = vim.api.nvim_get_runtime_file("", true),
            },
            diagnostics = { globals = { "vim" } },
            telemetry   = { enable = false },
          },
        },
      })

      -- emmet: sugerencias de elementos HTML/JSX
      vim.lsp.config("emmet_language_server", {
        filetypes = {
          "html", "css", "scss",
          "javascriptreact",
          "typescriptreact",
        },
      })
      vim.lsp.enable("emmet_language_server")

      -- jsonls con schemastore
      local ok, schemastore = pcall(require, "schemastore")
      if ok then
        vim.lsp.config("jsonls", {
          settings = {
            json = {
              schemas  = schemastore.json.schemas(),
              validate = { enable = true },
            },
          },
        })
      end
    end,
  },
}
