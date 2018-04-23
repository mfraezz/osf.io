<%inherit file="project/project_base.mako"/>
<%def name="title()">${node['title']} Security</%def>

<div class="page-header  visible-xs">
  <h2 class="text-300">Security</h2>
</div>

<div class="row">
    <div class="col-sm-5">
        <h2 class="break-word">
            TimeStampErrors
        </h2>
    </div>
    <div class="col-sm-7">
        <div id="toggleBar" class="pull-right"></div>
    </div>
</div>
<hr/>
<div class="row project-page">

    <!-- Begin left column -->
    <div class="col-md-3 col-xs-12 affix-parent scrollspy">
        <div class="panel panel-default osf-affix" data-spy="affix" data-offset-top="0" data-offset-bottom="263">
            <!-- Begin sidebar -->
            <ul class="nav nav-stacked nav-pills">
                <li class="active"><a href="#">TimestampErrors</a></li>
                <li><a href="#">&nbsp;</a></li>
            </ul>
        </div>
    </div>
 
    <div class="col-md-9 col-xs-12">
         <form id="security-form" class="form">
         <div class="panel panel-default">
             <div class="col-xs-12">
                 <div class="pull-right">
                   <span>
                         <button type="button"
                                     class="btn btn-default"
                                     id="btn-verify">Verify</button>
                         <button type="button"
                                     class="btn btn-success"
                                     id="btn-addtimestamp">Addtimestamp</button>
                   </span>
                 </div>
             </div>
             <span id="configureNodeAnchor" class="anchor"></span></div>
                 <table class="table table-bordered table-addon-terms">
                      <thead class="block-head">
                          <tr>
                              <th width="45%">FilePath</th>
                              <th width="15%">TimestampUpdateUser</th>
                              <th width="15%">TimestampUpdateDate</th>
                              <th widht="25%">TimestampVerification</th>
                          </tr>
                      </thead>
                      <div id="timestamp_errors_spinner" class="spinner-loading-wrapper">
                           <div class="logo-spin logo-lg"></div>
                           <p class="m-t-sm fg-load-message"> Loading timestamp error list ...  </p>
                      </div>
                      <tbody id="tree_timestamp_error_data">
                      </tbody>
                 </table>
             </span>
         </div>
         </form>
    </div>
</div>
<%def name="javascript_bottom()">
    ${parent.javascript_bottom()}
    % for script in tree_js:
        <script type="text/javascript" src="${script | webpack_asset}"></script>
    % endfor
    <script>
        window.contextVars.project_file_list = window.contextVars.project_file_list || {};
        window.contextVars.project_file_list = ${provider_list| sjson, n }
    </script>

    <script src=${"/static/public/js/security-page.js" | webpack_asset}></script>

</%def>
<script>
    $(function(){
        var btnVerify_onclick = function(event) {
            post_data = {}
            $.ajax({
                beforeSend: function(){
                    $("#timestamp_errors_spinner").show();
                },
                url: 'json/',
                data: post_data,
                dataType: 'json',
                async: false
            }).done(function(project_file_list) {
                var node_title = "${node['title']}";
                var project_tr = '<tr><td colspan="4">' + node_title + '</td></tr>';
                $(project_tr).appendTo($('#tree_timestamp_error_data'));
                var index = 0;
                project_file_list = project_file_list.provider_list;
                for (var i = 0; i < project_file_list.length; i++) {
                    var provider_tr = '<tr><td colspan="4">' + project_file_list[i].provider + '</td></tr>';
                    var file_list = project_file_list[i].provider_file_list;
                    var provider_output_flg = false;
                    for (var j = 0; j < file_list.length; j++) {
                        var post_data = {'provider': project_file_list[i].provider,
                                         'file_id': file_list[j].file_id,
                                         'file_path': file_list[j].file_path,
                                         'file_name': file_list[j].file_name,
                                         'version': file_list[j].version};
                        $.ajax({
                             beforeSend: function(){
                                  $("#timestamp_errors_spinner").show();
                             },
                             url:  nodeApiUrl + 'security/timestamp_error_data/',
                             data: post_data,
                             dataType: 'json',
                             async: false
                        })
                    }
                }
                console.log('end');
            }).fail(function(xhr, textStatus, error) {
               Raven.captureMessage('security json error', {
                   extra: {
                      url: url,
                      textStatus: textStatus,
                      error: error
                   }
               });
               errorFlg = true;
            });
            $("#security-form").submit();
        };

        var btnAddtimestamp_onclick = function(event) {
            inputCheckBoxs = $('[id=addTimestampCheck]:checked').map(function (index, el) {
                return $(this).val();
            });

            if (inputCheckBoxs.length == 0) {
                return false;
            }
            
            providerList = $('[id=provider]').map(function (index, el) {
                return $(this).val();
            });

            fileIdList = $('[id="file_id"]').map(function (index, el) {
                return $(this).val();
            });
            
            filePathList = $('[id=file_path]').map(function (index, el) {
                return $(this).val();
            });

            versionList = $('[id=version]').map(function (index, el) {
                return $(this).val();
            });

            fileNameList = $('[id=file_name]').map(function (index, el) {
                return $(this).val();
            });
            errorFlg = false;
            successCnt = 0;
            for (var i = 0; i < inputCheckBoxs.length; i++) {
                 index = inputCheckBoxs[i];
                 var post_data = {'provider': providerList[index],
                                  'file_id': fileIdList[index],
                                  'file_path': filePathList[index],
                                  'file_name': fileNameList[index],
                                  'version': versionList[index]};
                 $.ajax({
                     beforeSend: function(){
                       $("#timestamp_errors_spinner").show();
                     },
                     url: nodeApiUrl + 'security/add_timestamp/',
                     data: post_data,
                     dataType: 'json',
                     async: false
                 }).done(function(data) {
                     successCnt++;
                 }).fail(function(xhr, textStatus, error) {
                    Raven.captureMessage('timestamptoken add error', {
                        extra: {
                           url: url,
                           textStatus: textStatus,
                           error: error
                        }
                    });
                    errorFlg = true;
                 });
                 if (errorFlg) {
                     break;
                 }
            }
            if (errorFlg) {
                return;
            }
            $("#security-form").submit();
        };

        var document_onready = function (event) {
            $("#btn-verify").on("click", btnVerify_onclick);
            $("#btn-addtimestamp").on("click", btnAddtimestamp_onclick).focus();
        };

        $(document).ready(document_onready);
        $("#timestamp_errors_spinner").hide();
     });
</script>
