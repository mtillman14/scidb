library(shiny)
library(shinyjs)
library(plotly)
library(DT)

ui <- fluidPage(
  useShinyjs(),  # Initialize shinyjs
  tags$head(
    tags$style(HTML("
      .sidebar {
        max-height: 90vh;
        overflow-y: auto;
      }
      .main-panel, .tab-content, .tab-pane, .plotly {
        height: 100vh;
      }
      .plotly {
        width: 100%;
      }
      .fixed-buttons {
        position: absolute;
        bottom: 10px;
        width: 100%;
      }
      .data-table-container {
        max-height: 70vh; /* Adjust this value as needed */
        overflow-y: auto;
        overflow-x: auto;
      }
    "))
  ),
  sidebarLayout(
    sidebarPanel(
      class = "sidebar",
      width = 2,
      selectInput(
        inputId = "outcomeMeasureDropDown",
        label = "Variable to Plot",
        choices = NULL # Initially no choices
      ),
      tabsetPanel(
        tabPanel("Plot",
          checkboxGroupInput(
            inputId = "dataReductionFactorsCheckboxGroup",
            label = "Average Over Factors",
            choices = NULL
            ),
            selectInput(
              inputId = "tickFactorsselectInput",
              label = "XTick Factor Order",
              choices = NULL
            ),
            selectInput(
              inputId = "colorFactorSelectInput",
              label = "Color Factor",
              choices = NULL
            ),
            checkboxGroupInput(
              inputId = "facetFactorCheckboxGroup",
              label = "Facet Factors",
              choices = NULL
            )
            # checkboxGroupInput(
            #     inputId = "plotReplicateCheckboxGroup",
            #     label = "Plot Replication Factors",
            #     choices = NULL
            # )
        ),
        tabPanel("Stats",
          # Add content for Stats tab here
        )
      ),
      div(
        class = "fixed-buttons",
        actionButton("browseFileButton", "Browse File"),
        actionButton("runPlotButton", "Run Plot")
      )
    ),
    mainPanel(
      width = 10,
      textOutput("filePath"),
      tabsetPanel(
        tabPanel("Data Table",
          div(class = "data-table-container", DTOutput("dataTable"))  # Add DTOutput for the data table inside a scrollable div
        ),
        tabPanel("Grouped",
          plotlyOutput("plot", height = "90%")
        ),
        tabPanel("Relations", 
          # Add content for Relations tab here
        )
      ),      
      fluidRow(
        column(6, actionButton("exportButton", "Export")),
        column(6, actionButton("settingsButton", "Settings"))
      )
    )
  )
)