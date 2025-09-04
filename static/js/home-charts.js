// Register the datalabels plugin
Chart.register(ChartDataLabels);

// Helper function to format percentage labels
function getPercentageLabel(value, total) {
  if (total === 0) return '0%';
  var percentage = (value / total) * 100;
  return percentage.toFixed(1) + '%';
}

// Function to initialize all charts
function initializeCharts() {
  // Grading Distribution Chart
  if (typeof gradingData !== 'undefined' && gradingData) {
    var gradingCtx = document.getElementById('gradingChart').getContext('2d');
    var gradingTotal = gradingData.reduce((a, b) => a + b, 0);
    var gradingColors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'];
    
    var gradingChart = new Chart(gradingCtx, {
      type: 'doughnut',
      data: {
        labels: gradingLabels,
        datasets: [{
          data: gradingData,
          backgroundColor: gradingColors.slice(0, gradingLabels.length),
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
          },
          datalabels: {
            color: '#fff',
            font: {
              weight: 'bold'
            },
            formatter: function(value, context) {
              return getPercentageLabel(value, gradingTotal);
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return context.label + ': ' + context.raw + ' (' + getPercentageLabel(context.raw, gradingTotal) + ')';
              }
            }
          }
        }
      }
    });
  }
  
  // VCDR Ranges Chart (with adjusted cutoffs)
  if (typeof vcdrData !== 'undefined' && vcdrData) {
    var vcdrCtx = document.getElementById('vcdrChart').getContext('2d');
    var vcdrChart = new Chart(vcdrCtx, {
      type: 'bar',
      data: {
        labels: ['Right Eye', 'Left Eye'],
        datasets: [
          {
            label: 'Normal (< 0.5)',
            data: [vcdrData.normal_right, vcdrData.normal_left],
            backgroundColor: '#2ca02c'
          },
          {
            label: 'Borderline (0.5-0.7)',
            data: [vcdrData.borderline_right, vcdrData.borderline_left],
            backgroundColor: '#ff7f0e'
          },
          {
            label: 'Abnormal (0.7-0.8)',
            data: [vcdrData.abnormal_right, vcdrData.abnormal_left],
            backgroundColor: '#d62728'
          },
          {
            label: 'Severely Abnormal (≥ 0.8)',
            data: [vcdrData.severely_abnormal_right, vcdrData.severely_abnormal_left],
            backgroundColor: '#9467bd'
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            stacked: true,
            ticks: {
              precision: 0
            }
          },
          y: {
            stacked: true
          }
        },
        plugins: {
          datalabels: {
            display: false // No data labels for bar charts as requested
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return context.dataset.label + ': ' + context.raw;
              }
            }
          }
        }
      }
    });
  }
  
  // Ungradable Images Chart
  if (typeof ungradableData !== 'undefined' && ungradableData) {
    var ungradableCtx = document.getElementById('ungradableChart').getContext('2d');
    var ungradableTotal = ungradableData.graded + ungradableData.ungraded;
    var ungradableLabels = ['Gradable Images', 'Not Gradable Images'];
    
    var ungradableChart = new Chart(ungradableCtx, {
      type: 'doughnut',
      data: {
        labels: ungradableLabels,
        datasets: [{
          data: [ungradableData.graded, ungradableData.ungraded],
          backgroundColor: ['#2ca02c', '#d62728'],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
          },
          datalabels: {
            color: '#fff',
            font: {
              weight: 'bold'
            },
            formatter: function(value, context) {
              return getPercentageLabel(value, ungradableTotal);
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return context.label + ': ' + context.raw + ' (' + getPercentageLabel(context.raw, ungradableTotal) + ')';
              }
            }
          }
        }
      }
    });
  }
  
  // Images by Lab Unit and Disease Chart
  if (typeof imagesByLabUnitDiseaseData !== 'undefined' && imagesByLabUnitDiseaseData) {
    // Only process data if we have any
    if (imagesByLabUnitDiseaseData.length > 0) {
      // Process data for stacked bar chart
      var labUnitData = {};
      var diseaseSet = new Set();
      
      imagesByLabUnitDiseaseData.forEach(function(item) {
        if (!labUnitData[item.labUnit]) {
          labUnitData[item.labUnit] = {};
        }
        labUnitData[item.labUnit][item.disease] = item.count;
        diseaseSet.add(item.disease);
      });
      
      var diseases = Array.from(diseaseSet);
      var labUnits = Object.keys(labUnitData);
      
      // Create datasets for each disease
      var datasets = diseases.map(function(disease, index) {
        var colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];
        return {
          label: disease,
          data: labUnits.map(function(labUnit) {
            return labUnitData[labUnit][disease] || 0;
          }),
          backgroundColor: colors[index % colors.length]
        };
      });
      
      var labUnitDiseaseCtx = document.getElementById('labUnitDiseaseChart').getContext('2d');
      var labUnitDiseaseChart = new Chart(labUnitDiseaseCtx, {
        type: 'bar',
        data: {
          labels: labUnits,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              stacked: true,
              ticks: {
                precision: 0
              }
            },
            y: {
              stacked: true,
              ticks: {
                precision: 0
              }
            }
          },
          plugins: {
            datalabels: {
              display: false // No data labels for bar charts as requested
            },
            tooltip: {
              mode: 'index',
              intersect: false
            },
            legend: {
              position: 'right'
            }
          }
        }
      });
    }
  }
  
  // Verified Images by Lab Unit and Disease Chart
  if (typeof verifiedImagesByLabUnitDiseaseData !== 'undefined' && verifiedImagesByLabUnitDiseaseData) {
    // Only process data if we have any
    if (verifiedImagesByLabUnitDiseaseData.length > 0) {
      // Process data for percentage chart
      var verificationData = {};
      
      verifiedImagesByLabUnitDiseaseData.forEach(function(item) {
        var key = item.labUnit + ' - ' + item.disease;
        var percentage = item.total > 0 ? (item.verified / item.total) * 100 : 0;
        verificationData[key] = {
          percentage: percentage,
          total: item.total,
          verified: item.verified
        };
      });
      
      var verificationLabels = Object.keys(verificationData);
      var verificationPercentages = verificationLabels.map(function(key) {
        return verificationData[key].percentage;
      });
      
      var verifiedLabUnitDiseaseCtx = document.getElementById('verifiedLabUnitDiseaseChart').getContext('2d');
      var verifiedLabUnitDiseaseChart = new Chart(verifiedLabUnitDiseaseCtx, {
        type: 'bar',
        data: {
          labels: verificationLabels,
          datasets: [{
            label: 'Percentage Verified',
            data: verificationPercentages,
            backgroundColor: '#1f77b4'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              ticks: {
                callback: function(value) {
                  return value + '%';
                }
              }
            }
          },
          plugins: {
            datalabels: {
              color: '#000',
              font: {
                weight: 'bold'
              },
              formatter: function(value, context) {
                return value.toFixed(1) + '%';
              }
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  var key = context.label;
                  var data = verificationData[key];
                  return 'Verified: ' + data.verified + '/' + data.total + ' (' + data.percentage.toFixed(1) + '%)';
                }
              }
            }
          }
        }
      });
    }
  }
  
  // DR Impression Distribution Chart
  if (typeof drImpressionData !== 'undefined' && drImpressionData) {
    var drCtx = document.getElementById('drImpressionChart').getContext('2d');
    var drTotal = drImpressionData.reduce((a, b) => a + b, 0);
    
    var drChart = new Chart(drCtx, {
      type: 'pie',
      data: {
        labels: drImpressionLabels,
        datasets: [{
          data: drImpressionData,
          backgroundColor: [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
          ],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
          },
          datalabels: {
            color: '#fff',
            font: {
              weight: 'bold'
            },
            formatter: function(value, context) {
              return getPercentageLabel(value, drTotal);
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return context.label + ': ' + context.raw + ' (' + getPercentageLabel(context.raw, drTotal) + ')';
              }
            }
          }
        }
      }
    });
  }
  
  // Glaucoma Impression Distribution Chart
  if (typeof glaucomaImpressionData !== 'undefined' && glaucomaImpressionData) {
    var glaucomaCtx = document.getElementById('glaucomaImpressionChart').getContext('2d');
    var glaucomaTotal = glaucomaImpressionData.reduce((a, b) => a + b, 0);
    
    var glaucomaChart = new Chart(glaucomaCtx, {
      type: 'pie',
      data: {
        labels: glaucomaImpressionLabels,
        datasets: [{
          data: glaucomaImpressionData,
          backgroundColor: [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
          ],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
          },
          datalabels: {
            color: '#fff',
            font: {
              weight: 'bold'
            },
            formatter: function(value, context) {
              return getPercentageLabel(value, glaucomaTotal);
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return context.label + ': ' + context.raw + ' (' + getPercentageLabel(context.raw, glaucomaTotal) + ')';
              }
            }
          }
        }
      }
    });
  }
}

// Initialize charts when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  initializeCharts();
});